#!/usr/bin/env python3
"""Create and persist semantic links between SecondSelf wiki notes."""

from __future__ import annotations

import argparse
import hashlib
import pickle
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import frontmatter
import numpy as np

import config


EMBEDDINGS_PATH = config.DATA_DIR / "embeddings.pkl"
BODY_EXCERPT_CHARS = 1_500
RELATED_HEADING = "## Related"
RELATED_SECTION_PATTERN = re.compile(r"(?ms)^## Related\s*\n.*?(?=^##\s|\Z)")


@dataclass
class NoteRecord:
    """A parsed wiki note and the data needed for semantic linking."""

    path: Path
    post: frontmatter.Post
    id: str
    title: str
    summary: str
    body: str

    @property
    def content(self) -> str:
        # Generated links should not affect semantic similarity or invalidate cache entries.
        body_without_related = RELATED_SECTION_PATTERN.sub("", self.body).rstrip()
        return f"{self.title}\n{self.summary}\n{body_without_related[:BODY_EXCERPT_CHARS]}".strip()

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def load_wiki_notes() -> list[NoteRecord]:
    """Load every well-formed note under the PARA wiki folders."""
    notes: list[NoteRecord] = []
    seen_ids: set[str] = set()
    for path in sorted(config.WIKI_DIR.glob("*/*.md")):
        try:
            post = frontmatter.load(path)
            note_id = str(post.get("id", "")).strip()
            title = str(post.get("title", "")).strip()
            summary = str(post.get("summary", "")).strip()
        except Exception as exc:
            print(f"[WARNING] LNK-01: Skipping unreadable note '{path.name}': {exc}", file=sys.stderr)
            continue
        if not note_id or not title:
            print(f"[WARNING] LNK-02: Skipping '{path.name}' because id or title is missing.", file=sys.stderr)
            continue
        if note_id in seen_ids:
            print(f"[WARNING] LNK-03: Skipping duplicate note ID '{note_id}' in '{path.name}'.", file=sys.stderr)
            continue
        seen_ids.add(note_id)
        notes.append(NoteRecord(path, post, note_id, title, summary, post.content))
    return notes


def load_embedding_index() -> dict[str, dict[str, Any]]:
    """Load the persisted embedding index, ignoring a malformed legacy file."""
    if not EMBEDDINGS_PATH.exists():
        return {}
    try:
        with EMBEDDINGS_PATH.open("rb") as handle:
            index = pickle.load(handle)
        if not isinstance(index, dict):
            raise ValueError("index is not a dictionary")
        return index
    except (OSError, pickle.PickleError, ValueError, EOFError) as exc:
        print(f"[WARNING] LNK-04: Rebuilding invalid embedding index: {exc}", file=sys.stderr)
        return {}


def save_embedding_index(index: dict[str, dict[str, Any]]) -> None:
    """Persist embeddings in a compact, reusable index."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with EMBEDDINGS_PATH.open("wb") as handle:
        pickle.dump(index, handle)


def load_embedding_model() -> Any:
    """Load the configured local sentence-transformers model on demand (cached when running in Streamlit)."""
    try:
        import streamlit as st
        @st.cache_resource(show_spinner=False)
        def _get_cached_model(model_name: str):
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(model_name)
        return _get_cached_model(config.EMBEDDING_MODEL)
    except Exception:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed. Run: pip install -r requirements.txt") from exc
        return SentenceTransformer(config.EMBEDDING_MODEL)


def normalise_vector(vector: Any) -> np.ndarray:
    """Convert an embedding to a one-dimensional unit vector."""
    result = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(result)
    if norm == 0:
        raise ValueError("Embedding model returned a zero vector")
    return result / norm


def update_embedding_index(notes: Iterable[NoteRecord], index: dict[str, dict[str, Any]], model: Any | None = None) -> dict[str, dict[str, Any]]:
    """Encode only new or changed notes and discard embeddings for deleted notes."""
    notes = list(notes)
    current_ids = {note.id for note in notes}
    for note_id in list(index):
        if note_id not in current_ids:
            del index[note_id]

    to_encode = [note for note in notes if index.get(note.id, {}).get("content_hash") != note.content_hash]
    if not to_encode:
        return index
    model = model or load_embedding_model()
    vectors = model.encode([note.content for note in to_encode], convert_to_numpy=True, show_progress_bar=False)
    for note, vector in zip(to_encode, vectors, strict=True):
        index[note.id] = {
            "content_hash": note.content_hash,
            "embedding": normalise_vector(vector),
            "model": config.EMBEDDING_MODEL,
            "wiki_path": str(note.path.relative_to(config.ROOT)),
        }
    return index


def related_note_ids(note: NoteRecord, notes: Iterable[NoteRecord], index: dict[str, dict[str, Any]]) -> list[str]:
    """Return the most similar note IDs above the configured similarity threshold."""
    source = normalise_vector(index[note.id]["embedding"])
    candidates: list[tuple[float, str, str]] = []
    for candidate in notes:
        if candidate.id == note.id:
            continue
        score = float(np.dot(source, normalise_vector(index[candidate.id]["embedding"])))
        if score >= config.SIMILARITY_THRESHOLD:
            candidates.append((score, candidate.title.casefold(), candidate.id))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [note_id for _, _, note_id in candidates[: config.MAX_LINKS_PER_NOTE]]


def replace_related_section(body: str, links: list[str], notes_by_id: dict[str, NoteRecord]) -> str:
    """Replace the generated Related section while leaving the rest of the note intact."""
    body_without_related = RELATED_SECTION_PATTERN.sub("", body).rstrip()
    if links:
        lines = [RELATED_HEADING, ""]
        lines.extend(f"- [[{note_id}]] — {notes_by_id[note_id].title}" for note_id in links)
    else:
        lines = [RELATED_HEADING, "", "_No related notes found yet._"]
    return f"{body_without_related}\n\n" + "\n".join(lines)


def update_note_links(note: NoteRecord, links: list[str], notes_by_id: dict[str, NoteRecord]) -> bool:
    """Update a note's frontmatter and generated Related section when required."""
    new_body = replace_related_section(note.body, links, notes_by_id)
    old_links = note.post.get("links", [])
    if not isinstance(old_links, list):
        old_links = []
    changed = old_links != links or note.post.get("embedding_id") != note.id or note.post.content != new_body
    if not changed:
        return False
    note.post["links"] = links
    note.post["embedding_id"] = note.id
    note.post["updated_at"] = datetime.now().astimezone().isoformat()
    note.post.content = new_body
    note.path.write_text(frontmatter.dumps(note.post), encoding="utf-8")
    note.body = new_body
    return True


def find_note(note_id: str, notes: Iterable[NoteRecord]) -> NoteRecord:
    """Find a note using its full UUID or an unambiguous UUID prefix."""
    matches = [note for note in notes if note.id == note_id or note.id.startswith(note_id)]
    if not matches:
        raise ValueError(f"No wiki note matches ID '{note_id}'")
    if len(matches) > 1:
        raise ValueError(f"Note ID prefix '{note_id}' is ambiguous")
    return matches[0]


def link_notes(notes: list[NoteRecord], selected_notes: list[NoteRecord] | None = None, model: Any | None = None) -> tuple[int, int]:
    """Update embeddings and semantic links. Returns (notes_updated, index_size)."""
    if not notes:
        return 0, 0
    index = update_embedding_index(notes, load_embedding_index(), model)
    notes_by_id = {note.id: note for note in notes}
    targets = selected_notes if selected_notes is not None else notes
    updated = 0
    for note in targets:
        links = related_note_ids(note, notes, index)
        if update_note_links(note, links, notes_by_id):
            updated += 1
    save_embedding_index(index)
    return updated, len(index)


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf semantic auto-linking (Connect the Dots)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Embed and link every wiki note")
    group.add_argument("--note-id", metavar="ID", help="Embed all notes and update links for one note")
    args = parser.parse_args()

    notes = load_wiki_notes()
    if not notes:
        print("[INFO] No wiki notes found.")
        return 0
    targets: list[NoteRecord] | None = None
    if args.note_id:
        try:
            targets = [find_note(args.note_id, notes)]
        except ValueError as exc:
            print(f"[ERROR] LNK-05: {exc}", file=sys.stderr)
            return 1
    try:
        updated, index_size = link_notes(notes, targets)
    except Exception as exc:
        print(f"[ERROR] LNK-06: Could not generate semantic links: {exc}", file=sys.stderr)
        return 1
    print(f"[SUCCESS] Updated {updated} note(s); embedding index contains {index_size} note(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
