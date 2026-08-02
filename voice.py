#!/usr/bin/env python3
"""SecondSelf v2 — Voice Speech-to-Text Module (Phase 1)

Provides local audio transcription using Whisper/Faster-Whisper and audio recording management.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import config

# Lazy import for Whisper
_WHISPER_AVAILABLE = True
try:
    import whisper
except ImportError:
    _WHISPER_AVAILABLE = False


def is_whisper_available() -> bool:
    """Check if OpenAI Whisper package is installed."""
    return _WHISPER_AVAILABLE


# Base directory configuration for voice module
ROOT_DIR = Path(__file__).parent.resolve()
AUDIO_DIR = ROOT_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_audio_dir() -> Path:
    """Return valid audio storage path data/audio/."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIO_DIR


def get_groq_api_key() -> str:
    """Retrieve Groq API key safely from config or environment."""
    key = getattr(config, "GROQ_API_KEY", "")
    if not key:
        import os

        key = os.getenv("GROQ_API_KEY", "")
    return str(key)


def get_whisper_model() -> str:
    """Safely get Whisper model setting."""
    return str(getattr(config, "WHISPER_MODEL", "base"))


def save_audio_file(audio_source: Any, extension: str = ".wav") -> Path:
    """Save audio recording bytes, UploadedFile, dict, or memoryview to data/audio/ directory."""
    if isinstance(audio_source, dict):
        audio_bytes = audio_source.get("bytes") or audio_source.get("audio") or b""
    elif hasattr(audio_source, "read"):
        audio_bytes = audio_source.read()
    elif hasattr(audio_source, "getvalue"):
        audio_bytes = audio_source.getvalue()
    elif isinstance(audio_source, memoryview):
        audio_bytes = bytes(audio_source)
    elif isinstance(audio_source, bytes):
        audio_bytes = audio_source
    else:
        audio_bytes = bytes(audio_source)

    if not audio_bytes:
        raise ValueError("Audio bytes source is empty or invalid.")

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4()).split("-")[0]

    orig_name = getattr(audio_source, "name", f"rec_{now_str}_{short_id}{extension}")
    ext = Path(orig_name).suffix if Path(orig_name).suffix else extension
    filename = f"rec_{now_str}_{short_id}{ext}"

    audio_dir = get_audio_dir()
    audio_path = audio_dir / filename
    audio_path.write_bytes(audio_bytes)
    return audio_path


def transcribe_audio(audio_path: Path, model_name: Optional[str] = None) -> Dict[str, Any]:
    """Transcribe audio file using Groq Whisper API or local Whisper model.

    Returns dict with keys: 'text', 'language', 'audio_path', 'status', 'engine'.
    """
    if model_name is None:
        model_name = get_whisper_model()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # 1. Try Groq Audio Transcriptions API first
    groq_api_key = get_groq_api_key()
    if groq_api_key:
        try:
            from groq import Groq

            client = Groq(api_key=groq_api_key)
            with open(audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3-turbo",
                    response_format="json",
                )

            # Safely extract text whether response is a dict or a Transcription object
            if isinstance(transcription, dict):
                text = str(transcription.get("text", "")).strip()
            elif hasattr(transcription, "text"):
                text = str(transcription.text).strip()
            else:
                text = str(transcription).strip()

            root_dir = getattr(config, "ROOT", Path(__file__).parent.resolve())
            rel_audio_path = str(audio_path.relative_to(root_dir)) if audio_path.is_relative_to(root_dir) else str(audio_path)
            return {
                "text": text,
                "language": "en",
                "audio_path": rel_audio_path,
                "status": "success",
                "engine": "groq_whisper",
            }
        except Exception as exc:
            print(f"[WARNING] VOC-02: Groq audio transcription failed ({exc}). Trying local Whisper...")

    # 2. Fall back to local Whisper model if installed
    if is_whisper_available():
        try:
            model = whisper.load_model(model_name)
            result = model.transcribe(str(audio_path))
            root_dir = getattr(config, "ROOT", Path(__file__).parent.resolve())
            rel_audio_path = str(audio_path.relative_to(root_dir)) if audio_path.is_relative_to(root_dir) else str(audio_path)
            return {
                "text": text,
                "language": language,
                "audio_path": rel_audio_path,
                "status": "success",
                "engine": "local_whisper",
            }
        except Exception as exc:
            print(f"[ERROR] VOC-01: Local Whisper transcription failed: {exc}")
            root_dir = getattr(config, "ROOT", Path(__file__).parent.resolve())
            rel_audio_path = str(audio_path.relative_to(root_dir)) if audio_path.is_relative_to(root_dir) else str(audio_path)
            return {
                "text": "",
                "language": "en",
                "audio_path": rel_audio_path,
                "status": f"error: {exc}",
                "engine": "local_whisper",
            }

    root_dir = getattr(config, "ROOT", Path(__file__).parent.resolve())
    rel_audio_path = str(audio_path.relative_to(root_dir)) if audio_path.is_relative_to(root_dir) else str(audio_path)
    return {
        "text": "",
        "language": "en",
        "audio_path": rel_audio_path,
        "status": "error_no_transcription_engine",
        "engine": "none",
    }


if __name__ == "__main__":
    print("=== SecondSelf v2 — Voice Service Status ===")
    print(f"Whisper Available: {is_whisper_available()}")
    print(f"Whisper Model Setting: {get_whisper_model()}")
    print(f"Audio Directory: {get_audio_dir()}")
