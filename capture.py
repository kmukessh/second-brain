#!/usr/bin/env python3
"""
SecondSelf — Capture Pipeline (capture.py)
Phase 1: The Archivist

One command captures any note, link, or file into raw/ with timestamp + unique ID + sidecar metadata.
"""

import sys
import os
import uuid
import hashlib
import shutil
import json
from datetime import datetime
import argparse
from typing import Optional, Tuple
import requests

import config
from models import CaptureMetadata


def generate_uuid() -> Tuple[str, str]:
    """Returns full UUID string and short 8-char ID prefix."""
    full_id = str(uuid.uuid4())
    short_id = full_id.split("-")[0]
    return full_id, short_id


def get_timestamp_prefix(short_id: str) -> str:
    """Generate filename prefix: YYYYMMDD_HHMMSS_{short_id}."""
    now = datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{short_id}"


def compute_sha256_text(text: str) -> str:
    """Compute SHA-256 hash of a string."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def compute_sha256_file(file_path: os.PathLike) -> str:
    """Compute SHA-256 hash of a file on disk."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def check_existing_hash(content_hash: str) -> Optional[str]:
    """Check if content_hash already exists in raw/*.meta.json."""
    for meta_file in config.RAW_DIR.glob("*.meta.json"):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("content_hash") == content_hash:
                    return data.get("id")
        except Exception:
            continue
    return None


def save_sidecar_metadata(meta: CaptureMetadata, prefix: str) -> str:
    """Save sidecar metadata JSON to raw/{prefix}.meta.json."""
    meta_path = config.RAW_DIR / f"{prefix}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, indent=2)
    return str(meta_path)


def capture_note(note_text: str) -> str:
    """Capture a raw text note."""
    text = note_text.strip()
    if not text:
        print("[ERROR] CAP-01: Note text cannot be empty.")
        sys.exit(1)

    full_id, short_id = generate_uuid()
    prefix = get_timestamp_prefix(short_id)
    content_hash = compute_sha256_text(text)

    existing_id = check_existing_hash(content_hash)
    if existing_id:
        print(f"[WARNING] CAP-07: Duplicate content detected (matches capture ID {existing_id}). Continuing capture...")

    raw_filename = f"{prefix}.txt"
    raw_path = config.RAW_DIR / raw_filename

    with open(raw_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)

    iso_timestamp = datetime.now().astimezone().isoformat()
    meta = CaptureMetadata(
        id=full_id,
        captured_at=iso_timestamp,
        type="note",
        source="cli",
        original_filename=None,
        content_hash=content_hash,
        processed=False,
        wiki_path=None,
        raw_file=str(raw_path.relative_to(config.ROOT))
    )

    save_sidecar_metadata(meta, prefix)
    print(f"[SUCCESS] Captured text note -> {raw_path.name} (ID: {short_id})")
    return full_id


def capture_url(url_string: str) -> str:
    """Capture a web URL and fetch initial body/title preview."""
    url = url_string.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    full_id, short_id = generate_uuid()
    prefix = get_timestamp_prefix(short_id)

    raw_filename = f"{prefix}.url"
    raw_path = config.RAW_DIR / raw_filename

    fetched_content = f"URL: {url}\n"
    print(f"[INFO] Fetching URL preview for {url}...")
    try:
        headers = {"User-Agent": "SecondSelf-Archivist/1.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        fetched_content += f"\n--- Fetched Page Content ---\n{resp.text[:5000]}"
    except Exception as e:
        print(f"[WARNING] CAP-03: Failed to fetch live URL content ({e}). Saving URL reference only.")
        fetched_content += f"\n[Fetch Warning: {e}]"

    with open(raw_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(fetched_content)

    content_hash = compute_sha256_text(url)
    iso_timestamp = datetime.now().astimezone().isoformat()
    meta = CaptureMetadata(
        id=full_id,
        captured_at=iso_timestamp,
        type="link",
        source="cli",
        original_filename=None,
        content_hash=content_hash,
        processed=False,
        wiki_path=None,
        raw_file=str(raw_path.relative_to(config.ROOT))
    )

    save_sidecar_metadata(meta, prefix)
    print(f"[SUCCESS] Captured link -> {raw_path.name} (ID: {short_id})")
    return full_id


def capture_file(file_path_str: str) -> str:
    """Capture a file by copying it into raw/."""
    from pathlib import Path
    src_path = Path(file_path_str) if Path(file_path_str).is_absolute() else (config.ROOT / file_path_str)
    
    if not src_path.exists() or not src_path.is_file():
        print(f"[ERROR] CAP-02: File '{file_path_str}' does not exist or is not a valid file.")
        sys.exit(1)

    file_size_mb = src_path.stat().st_size / (1024 * 1024)
    if file_size_mb > config.MAX_FILE_SIZE_MB:
        print(f"[ERROR] CAP-05: File size ({file_size_mb:.2f} MB) exceeds maximum allowed ({config.MAX_FILE_SIZE_MB} MB).")
        sys.exit(1)

    full_id, short_id = generate_uuid()
    prefix = get_timestamp_prefix(short_id)

    orig_name = src_path.name
    ext = src_path.suffix
    if not ext:
        ext = ".bin"

    raw_filename = f"{prefix}{ext}"
    dest_path = config.RAW_DIR / raw_filename

    shutil.copy2(src_path, dest_path)
    content_hash = compute_sha256_file(dest_path)

    existing_id = check_existing_hash(content_hash)
    if existing_id:
        print(f"[WARNING] CAP-07: Duplicate file hash detected (matches capture ID {existing_id}).")

    iso_timestamp = datetime.now().astimezone().isoformat()
    meta = CaptureMetadata(
        id=full_id,
        captured_at=iso_timestamp,
        type="file",
        source="cli",
        original_filename=orig_name,
        content_hash=content_hash,
        processed=False,
        wiki_path=None,
        raw_file=str(dest_path.relative_to(config.ROOT))
    )

    save_sidecar_metadata(meta, prefix)
    print(f"[SUCCESS] Captured file -> {dest_path.name} (ID: {short_id})")
    return full_id


def main():
    parser = argparse.ArgumentParser(description="SecondSelf — Capture Pipeline (The Archivist)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--note", type=str, help="Capture raw text note")
    group.add_argument("--url", type=str, help="Capture URL bookmark/webpage")
    group.add_argument("--file", type=str, help="Capture file (PDF, TXT, MD, etc.)")

    args = parser.parse_args()

    if args.note is not None:
        capture_note(args.note)
    elif args.url is not None:
        capture_url(args.url)
    elif args.file is not None:
        capture_file(args.file)


if __name__ == "__main__":
    main()
