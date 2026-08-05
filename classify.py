#!/usr/bin/env python3
"""Classify unprocessed SecondSelf captures into PARA wiki notes."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import frontmatter
from groq import Groq
from pypdf import PdfReader

import config
from models import CaptureMetadata, WikiNote


PARA_CATEGORIES = {"Projects", "Areas", "Resources", "Archives"}
MAX_PROMPT_CHARS = 12_000


def load_unprocessed_raw() -> list[tuple[Path, CaptureMetadata]]:
    """Return valid, unprocessed raw capture sidecars in chronological order."""
    captures: list[tuple[Path, CaptureMetadata]] = []
    for meta_path in sorted(config.RAW_DIR.glob("*.meta.json")):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            metadata = CaptureMetadata.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            print(f"[WARNING] CLS-01: Skipping invalid metadata '{meta_path.name}': {exc}")
            continue
        if not metadata.processed:
            captures.append((meta_path, metadata))
        elif metadata.wiki_path:
            w_path = config.ROOT / metadata.wiki_path
            if not w_path.exists():
                metadata.processed = False
                captures.append((meta_path, metadata))
    return captures


def raw_path_for(metadata: CaptureMetadata, meta_path: Path) -> Path:
    """Resolve a raw file path stored relative to the repository root."""
    if metadata.raw_file:
        return config.ROOT / Path(metadata.raw_file)
    return meta_path.with_name(meta_path.name.removesuffix(".meta.json"))


def extract_text(raw_path: Path) -> str:
    """Extract textual content from supported raw files (.txt, .url, .md, .pdf)."""
    if not raw_path.exists() or not raw_path.is_file():
        raise FileNotFoundError(f"Raw capture file not found: {raw_path}")

    suffix = raw_path.suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(raw_path))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # pypdf exposes several parser exceptions
            raise ValueError(f"Could not read PDF '{raw_path.name}': {exc}") from exc
    elif suffix in {".txt", ".url", ".md", ".markdown"}:
        text = raw_path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported capture type '{suffix or '[no extension]'}' for '{raw_path.name}'")

    text = text.strip()
    if not text:
        raise ValueError(f"No extractable text found in '{raw_path.name}'")
    return text


def _json_from_response(content: str) -> dict[str, Any]:
    """Parse JSON, accepting a Markdown code fence from older model responses."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("Model response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON must be an object")
    return parsed


from calendar_service import create_event as create_calendar_event, is_schedulable_event


def _normalise_classification(data: dict[str, Any], body: str = "") -> dict[str, Any]:
    category = str(data.get("para_category", "")).strip().title()
    if category not in PARA_CATEGORIES:
        raise ValueError(f"Invalid PARA category '{data.get('para_category')}'")

    title = re.sub(r"\s+", " ", str(data.get("title", "")).strip())
    if not title:
        raise ValueError("Classification title cannot be empty")

    tags_value = data.get("tags", [])
    if not isinstance(tags_value, list):
        raise ValueError("Classification tags must be an array")
    tags = []
    for tag in tags_value:
        cleaned = re.sub(r"\s+", " ", str(tag).strip().lstrip("#"))
        if cleaned and cleaned.lower() not in {item.lower() for item in tags}:
            tags.append(cleaned)

    summary = re.sub(r"\s+", " ", str(data.get("summary", "")).strip())
    if not summary:
        raise ValueError("Classification summary cannot be empty")

    # Detect if content contains explicit schedule intent for today or future date
    text_check = f"{title} {summary} {body}"
    is_schedulable, _, _, _ = is_schedulable_event(text_check)

    if is_schedulable:
        for t in ["meeting", "event", "scheduled"]:
            if t not in [x.lower() for x in tags]:
                tags.append(t)

    if not 2 <= len(tags) <= 6:
        if len(tags) < 2:
            tags.extend(["capture", "note"])
        tags = tags[:6]

    return {
        "para_category": category,
        "title": title,
        "tags": tags,
        "summary": summary,
        "is_meeting": is_schedulable,
    }


def call_llm_classify(content: str, client: Groq | None = None) -> dict[str, Any]:
    """Ask Groq for a validated PARA classification of capture content."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured. Add it to .env before classifying captures.")
    client = client or Groq(api_key=config.GROQ_API_KEY)
    prompt_content = content[:MAX_PROMPT_CHARS]
    prompt = f"""You are a personal knowledge organizer using the PARA method.
Classify the capture below. Return only a JSON object with exactly these fields:
- para_category: one of Projects, Areas, Resources, Archives
- title: concise descriptive title
- tags: array of 2 to 5 short, distinct tags
- summary: one sentence describing the capture

Capture:
{prompt_content}"""
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content_response = response.choices[0].message.content
    if not content_response:
        raise ValueError("Model returned an empty classification")
    return _normalise_classification(_json_from_response(content_response), body=content)


def slugify(value: str) -> str:
    """Create a portable, readable filename stem from a note title."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:80].rstrip("-") or "untitled"


def write_wiki_note(metadata: CaptureMetadata, classification: dict[str, Any], body: str) -> Path:
    """Write a Markdown note with YAML frontmatter into its PARA directory."""
    note_id = metadata.id.split("-")[0]
    timestamp = datetime.now().astimezone().isoformat()
    
    text_check = f"{body}\n{classification.get('title', '')}\n{classification.get('summary', '')}"
    is_schedulable, summary_title, start_dt, reason = is_schedulable_event(text_check)
    
    cal_event_id = None
    cal_event_link = None
    cal_account = config.DEFAULT_GOOGLE_ACCOUNT
    cal_start = None
    cal_end = None
    cal_status = None
    cal_error = None

    # Automatically schedule Google Calendar event and reminder ONLY if it contains schedule intent AND is today/future
    if is_schedulable:
        try:
            event_title = summary_title if summary_title and len(summary_title) >= 3 else classification["title"]
            cal_res = create_calendar_event(
                summary=event_title,
                start_time=start_dt,
                description=f"{classification['summary']}\n\nCaptured from SecondSelf: {metadata.raw_file or ''}",
                target_account=cal_account,
            )
            cal_status = cal_res.get("status")
            evt = cal_res.get("event", {})
            if evt:
                cal_event_id = evt.get("id")
                cal_event_link = evt.get("html_link")
                cal_start = evt.get("start_time")
                cal_end = evt.get("end_time")
            if cal_status in ("success", "preview"):
                print(f"[SUCCESS] Scheduled Google Calendar event & reminder for '{event_title}' ({cal_account})")
            else:
                cal_status = "failed"
                cal_error = str(cal_res.get("error") or cal_res.get("message") or "Google Calendar did not create the event.")
                print(f"[WARNING] CLS-CAL: Calendar event was not created: {cal_error}", file=sys.stderr)
        except Exception as exc:
            cal_status = "failed"
            cal_error = str(exc)
            print(f"[WARNING] CLS-CAL: Could not create calendar event ({exc})", file=sys.stderr)
    else:
        print(f"[INFO] CLS-CAL: Skipping calendar scheduling ({reason})")


    wiki_note = WikiNote(
        id=metadata.id,
        title=classification["title"],
        para_category=classification["para_category"],
        tags=classification["tags"],
        summary=classification["summary"],
        created_at=metadata.captured_at,
        updated_at=timestamp,
        source_raw=metadata.raw_file,
        body=body,
        is_meeting=is_schedulable,
        calendar_event_id=cal_event_id,
        calendar_event_link=cal_event_link,
        calendar_account=cal_account if is_schedulable else None,
        calendar_event_start=cal_start,
        calendar_event_end=cal_end,
        calendar_event_status=cal_status,
        calendar_event_error=cal_error,
    )
    destination = config.WIKI_DIR / wiki_note.para_category / f"{slugify(wiki_note.title)}-{note_id}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(wiki_note.body, **wiki_note.to_frontmatter_dict())
    destination.write_text(frontmatter.dumps(post), encoding="utf-8")
    return destination



def mark_raw_processed(meta_path: Path, metadata: CaptureMetadata, wiki_path: Path) -> None:
    """Persist processing state only after the wiki note has been written."""
    metadata.processed = True
    metadata.wiki_path = str(wiki_path.relative_to(config.ROOT))
    meta_path.write_text(json.dumps(metadata.to_dict(), indent=2) + "\n", encoding="utf-8")


def find_capture(capture_id: str, captures: Iterable[tuple[Path, CaptureMetadata]]) -> tuple[Path, CaptureMetadata]:
    matches = [(path, meta) for path, meta in captures if meta.id == capture_id or meta.id.startswith(capture_id)]
    if not matches:
        raise ValueError(f"No unprocessed capture matches ID '{capture_id}'")
    if len(matches) > 1:
        raise ValueError(f"Capture ID prefix '{capture_id}' is ambiguous")
    return matches[0]


def fallback_classify(body: str) -> dict[str, Any]:
    """Generate a valid fallback classification when LLM call fails."""
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    first_line = lines[0] if lines else "Captured Note"
    clean_title = re.sub(r"^#+\s*", "", first_line).strip()[:60] or "Captured Note"
    summary = body[:150].replace("\n", " ").strip() or "Captured knowledge note."
    text_check = f"{clean_title} {summary} {body}".lower()
    meeting_kws = ["meeting", "interview", "session", "schedule", "call", "appointment", "live session"]
    is_meeting = any(kw in text_check for kw in meeting_kws)
    tags = ["capture", "resource"]
    if is_meeting:
        tags.extend(["meeting", "event"])
    return {
        "para_category": "Resources",
        "title": clean_title,
        "tags": tags,
        "summary": summary,
        "is_meeting": is_meeting,
    }


def classify_capture(meta_path: Path, metadata: CaptureMetadata) -> Path:
    """Classify one capture, write its note, then mark its sidecar as processed."""
    body = extract_text(raw_path_for(metadata, meta_path))
    try:
        classification = call_llm_classify(body)
    except Exception as exc:
        print(f"[WARNING] CLS-02: LLM classification fallback for {metadata.id.split('-')[0]}: {exc}", file=sys.stderr)
        classification = fallback_classify(body)

    wiki_path = write_wiki_note(metadata, classification, body)
    mark_raw_processed(meta_path, metadata, wiki_path)
    return wiki_path



def classify_all_unprocessed() -> int:
    """Classify all unprocessed raw captures."""
    captures = load_unprocessed_raw()
    if not captures:
        return 0
    failures = 0
    for meta_path, metadata in captures:
        try:
            wiki_path = classify_capture(meta_path, metadata)
            print(f"[SUCCESS] Classified {metadata.id.split('-')[0]} -> {wiki_path.relative_to(config.ROOT)}")
        except Exception as exc:
            failures += 1
            print(f"[ERROR] CLS-03: Could not classify {metadata.id.split('-')[0]}: {exc}", file=sys.stderr)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf auto-classification (The Sorting Hat)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Classify every unprocessed raw capture")
    group.add_argument("--id", metavar="ID", help="Classify one unprocessed capture by UUID or prefix")
    args = parser.parse_args()

    captures = load_unprocessed_raw()
    if args.id:
        try:
            captures = [find_capture(args.id, captures)]
        except ValueError as exc:
            print(f"[ERROR] CLS-02: {exc}", file=sys.stderr)
            return 1
    if not captures:
        print("[INFO] No unprocessed captures found.")
        return 0

    failures = classify_all_unprocessed()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
