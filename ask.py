#!/usr/bin/env python3
"""SecondSelf RAG Q&A (Week 4.1: The Oracle)

Embeds user question, retrieves relevant top-k wiki notes using cosine similarity,
builds a prompt context, and calls Groq LLM to synthesize a cited answer.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import frontmatter
import numpy as np
from groq import Groq

import config
from models import AskResponse, AskSource


RAG_MIN_SIMILARITY = 0.35  # Enforce minimum similarity threshold for RAG retrieval


def load_embedding_index(embeddings_path: Path = config.DATA_DIR / "embeddings.pkl") -> Dict[str, Dict[str, Any]]:
    """Load the persisted embedding index from data/embeddings.pkl."""
    if not embeddings_path.exists():
        return {}
    try:
        with embeddings_path.open("rb") as handle:
            index = pickle.load(handle)
        if isinstance(index, dict):
            return index
        return {}
    except Exception as exc:
        print(f"[WARNING] ASK-01: Could not load embedding index: {exc}", file=sys.stderr)
        return {}


_GLOBAL_EMBEDDING_MODEL: Any = None


def load_embedding_model(force_fresh: bool = False) -> Any:
    """Load sentence-transformers model on demand with process-level singleton and local files preference."""
    global _GLOBAL_EMBEDDING_MODEL
    if not force_fresh and _GLOBAL_EMBEDDING_MODEL is not None:
        return _GLOBAL_EMBEDDING_MODEL

    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    try:
        from sentence_transformers import SentenceTransformer
        try:
            model_inst = SentenceTransformer(config.EMBEDDING_MODEL, local_files_only=True)
        except Exception:
            model_inst = SentenceTransformer(config.EMBEDDING_MODEL)
        
        _GLOBAL_EMBEDDING_MODEL = model_inst
        return _GLOBAL_EMBEDDING_MODEL
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is not installed. Run: pip install -r requirements.txt") from exc


def normalize_vector(vec: Any) -> np.ndarray:
    """Convert an embedding to a unit vector."""
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(arr)
    if norm == 0:
        raise ValueError("Zero vector encountered in embedding")
    return arr / norm


def retrieve_relevant_notes(
    query_vector: np.ndarray,
    index: Dict[str, Dict[str, Any]],
    top_k: int = config.RAG_TOP_K,
    min_similarity: float = RAG_MIN_SIMILARITY,
) -> List[Tuple[str, float]]:
    """Compare query vector against note embeddings and return top-k (note_id, similarity_score)."""
    scores: List[Tuple[str, float]] = []
    q_norm = normalize_vector(query_vector)

    for note_id, data in index.items():
        if not isinstance(data, dict) or "embedding" not in data:
            continue
        try:
            n_norm = normalize_vector(data["embedding"])
            score = float(np.dot(q_norm, n_norm))
            if score >= min_similarity:
                scores.append((note_id, score))
        except Exception:
            continue

    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def load_note_content(note_id: str) -> Optional[Dict[str, Any]]:
    """Find and parse wiki note content by note ID."""
    for path in config.WIKI_DIR.glob("*/*.md"):
        if path.name.startswith("."):
            continue
        try:
            post = frontmatter.load(path)
            if str(post.get("id", "")).strip() == note_id:
                try:
                    rel_path = str(path.relative_to(config.ROOT)).replace("\\", "/")
                except ValueError:
                    rel_path = str(path).replace("\\", "/")

                return {
                    "id": note_id,
                    "title": str(post.get("title", path.stem)).strip(),
                    "category": str(post.get("para_category", path.parent.name)).strip(),
                    "tags": post.get("tags", []),
                    "summary": str(post.get("summary", "")).strip(),
                    "wiki_path": rel_path,
                    "body": post.content.strip(),
                }
        except Exception:
            continue
    return None


def ask(
    question: str,
    top_k: int = config.RAG_TOP_K,
    min_similarity: float = RAG_MIN_SIMILARITY,
    model: Any = None,
    client: Optional[Groq] = None,
) -> AskResponse:
    """RAG Q&A query over SecondSelf wiki notes."""
    global _GLOBAL_EMBEDDING_MODEL
    question = question.strip()
    if not question:
        return AskResponse(answer="Please provide a non-empty question.", sources=[])

    if not config.GROQ_API_KEY:
        return AskResponse(
            answer="[ERROR] GROQ_API_KEY is not configured in environment or .env file.",
            sources=[],
        )

    # Load embedding index
    index = load_embedding_index()
    if not index:
        return AskResponse(
            answer="I don't have information on this in your Second Brain (no indexed notes found).",
            sources=[],
        )

    # Embed query with recovery for closed clients
    try:
        model_instance = model or load_embedding_model()
        query_vector = model_instance.encode(question, convert_to_numpy=True, show_progress_bar=False)
    except Exception as exc:
        try:
            _GLOBAL_EMBEDDING_MODEL = None
            fresh_model = load_embedding_model(force_fresh=True)
            query_vector = fresh_model.encode(question, convert_to_numpy=True, show_progress_bar=False)
        except Exception as retry_exc:
            return AskResponse(
                answer=f"[ERROR] Could not compute question embedding: {retry_exc}",
                sources=[],
            )



    # Retrieve relevant notes
    relevant = retrieve_relevant_notes(query_vector, index, top_k=top_k, min_similarity=min_similarity)
    if not relevant:
        return AskResponse(
            answer="I don't have information on this in your Second Brain.",
            sources=[],
        )

    # Load note contents & build sources list
    retrieved_notes: List[Dict[str, Any]] = []
    sources: List[AskSource] = []

    for note_id, score in relevant:
        note_data = load_note_content(note_id)
        if note_data:
            retrieved_notes.append(note_data)
            sources.append(
                AskSource(
                    id=note_data["id"],
                    title=note_data["title"],
                    wiki_path=note_data["wiki_path"],
                    score=round(score, 4),
                )
            )

    if not retrieved_notes:
        return AskResponse(
            answer="I don't have information on this in your Second Brain.",
            sources=[],
        )

    # Build context prompt
    context_blocks = []
    for idx, note in enumerate(retrieved_notes, start=1):
        context_blocks.append(
            f"Source [{idx}] (ID: {note['id']}, Title: {note['title']}, Category: {note['category']}):\n"
            f"Summary: {note['summary']}\n"
            f"Content:\n{note['body'][:2500]}\n"
        )
    context_str = "\n---\n".join(context_blocks)

    system_prompt = (
        "You are SecondSelf, an intelligent second brain assistant.\n"
        "Answer the user's question strictly and ONLY using the provided source notes below.\n\n"
        "FORMATTING & DISPLAY RULES:\n"
        "1. Always format lists, schedules, and multi-item answers line-by-line using clean Markdown bullet points.\n"
        "2. Put EVERY schedule, meeting, or list item on its OWN separate line with a clean line break.\n"
        "3. For schedules/events, format each line like: `- 📅 **Date/Time**: Event Title (Source [X])`.\n"
        "4. NEVER collapse list items or schedules into a single paragraph or inline text block.\n"
        "5. Do not hallucinate or use outside knowledge. Cite sources clearly (e.g. Source [1]).\n"
        "6. If the answer cannot be deduced from the provided notes, respond strictly: "
        "\"I don't have information on this in your Second Brain.\""
    )

    user_prompt = f"<context>\n{context_str}\n</context>\n\nQuestion: {question}"

    try:
        client = client or Groq(api_key=config.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        answer = response.choices[0].message.content or "I don't have information on this in your Second Brain."
        return AskResponse(answer=answer.strip(), sources=sources)
    except Exception as exc:
        return AskResponse(
            answer=f"[ERROR] LLM synthesis failed: {exc}",
            sources=sources,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf RAG Q&A (Week 4.1: The Oracle)")
    parser.add_argument("question", nargs="?", help="The question to ask your Second Brain")
    args = parser.parse_args()

    if not args.question:
        parser.print_help()
        return 1

    res = ask(args.question)
    print("\n=== SecondSelf Answer ===")
    print(res.answer)
    if res.sources:
        print("\n=== Sources Cited ===")
        for s in res.sources:
            print(f"- {s.title} ({s.wiki_path}) [Score: {s.score:.2%}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
