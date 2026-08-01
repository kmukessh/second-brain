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


def save_audio_file(audio_bytes: bytes, extension: str = ".wav") -> Path:
    """Save audio recording bytes to data/audio/ directory."""
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4()).split("-")[0]
    filename = f"rec_{now_str}_{short_id}{extension}"
    audio_path = config.AUDIO_DIR / filename
    audio_path.write_bytes(audio_bytes)
    return audio_path


def transcribe_audio(audio_path: Path, model_name: str = config.WHISPER_MODEL) -> Dict[str, Any]:
    """Transcribe audio file locally using Whisper model.

    Returns dict with keys: 'text', 'language', 'audio_path'.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if not is_whisper_available():
        return {
            "text": "[Whisper library not installed. Install via `pip install openai-whisper`]",
            "language": "en",
            "audio_path": str(audio_path.relative_to(config.ROOT)),
            "status": "error_missing_whisper",
        }

    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path))
        text = str(result.get("text", "")).strip()
        language = str(result.get("language", "en"))
        return {
            "text": text,
            "language": language,
            "audio_path": str(audio_path.relative_to(config.ROOT)),
            "status": "success",
        }
    except Exception as exc:
        print(f"[ERROR] VOC-01: Whisper transcription failed: {exc}")
        return {
            "text": "",
            "language": "en",
            "audio_path": str(audio_path.relative_to(config.ROOT)),
            "status": f"error: {exc}",
        }


if __name__ == "__main__":
    print("=== SecondSelf v2 — Voice Service Status ===")
    print(f"Whisper Available: {is_whisper_available()}")
    print(f"Whisper Model Setting: {config.WHISPER_MODEL}")
    print(f"Audio Directory: {config.AUDIO_DIR}")
