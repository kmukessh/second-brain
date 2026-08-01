#!/usr/bin/env python3
"""SecondSelf Graph Builder (Week 3.1: Give It a Shape)

Scans wiki notes in wiki/**/*.md, parses frontmatter and links,
computes node degree for sizing and similarity weights for edges,
and exports clean graph JSON to data/graph.json.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import frontmatter
import numpy as np

import config
from models import GraphEdge, GraphNode


RELATED_SECTION_PATTERN = re.compile(r"(?ms)^## Related\s*\n.*?(?=^##\s|\Z)")
WIKILINK_PATTERN = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]")


def load_embeddings(embeddings_path: Path) -> Dict[str, np.ndarray]:
    """Load normalized embedding vectors from embeddings.pkl if available."""
    if not embeddings_path.exists():
        return {}
    try:
        with embeddings_path.open("rb") as handle:
            raw_index = pickle.load(handle)
        if not isinstance(raw_index, dict):
            return {}
        vectors: Dict[str, np.ndarray] = {}
        for note_id, data in raw_index.items():
            if isinstance(data, dict) and "embedding" in data:
                vec = np.asarray(data["embedding"], dtype=np.float32).reshape(-1)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vectors[note_id] = vec / norm
        return vectors
    except Exception as exc:
        print(f"[WARNING] GRP-00: Failed to load embeddings from {embeddings_path}: {exc}", file=sys.stderr)
        return {}


def parse_wiki_notes(wiki_dir: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Scan wiki directory and return (notes_by_id, id_lookup).

    id_lookup maps title/slug/short_id to full note_id.
    """
    notes_by_id: Dict[str, Dict[str, Any]] = {}
    id_lookup: Dict[str, str] = {}

    for path in sorted(wiki_dir.glob("*/*.md")):
        if path.name.startswith("."):
            continue
        try:
            post = frontmatter.load(path)
        except Exception as exc:
            print(f"[WARNING] GRP-01: Skipping unreadable note '{path.name}': {exc}", file=sys.stderr)
            continue

        note_id = str(post.get("id", "")).strip()
        title = str(post.get("title", path.stem)).strip()

        if not note_id:
            print(f"[WARNING] GRP-02: Skipping note without ID in '{path.name}'.", file=sys.stderr)
            continue

        category = str(post.get("para_category", path.parent.name)).strip()
        tags = post.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)]
        tags = [str(t) for t in tags]

        summary = str(post.get("summary", "")).strip()

        # Calculate relative path with forward slashes for cross-platform compatibility
        try:
            rel_path = str(path.relative_to(config.ROOT)).replace("\\", "/")
        except ValueError:
            rel_path = str(path).replace("\\", "/")

        frontmatter_links = post.get("links", [])
        if not isinstance(frontmatter_links, list):
            frontmatter_links = []
        frontmatter_links = [str(l).strip() for l in frontmatter_links if str(l).strip()]

        notes_by_id[note_id] = {
            "id": note_id,
            "title": title,
            "category": category,
            "tags": tags,
            "summary": summary,
            "wiki_path": rel_path,
            "frontmatter_links": frontmatter_links,
            "content": post.content,
            "path": path,
        }

        # Index note_id and lookups
        id_lookup[note_id.casefold()] = note_id
        # Also index short ID (first 8 chars if UUID format)
        if len(note_id) >= 8:
            short_id = note_id[:8].casefold()
            if short_id not in id_lookup:
                id_lookup[short_id] = note_id
        # Also index title
        id_lookup[title.casefold()] = note_id

    return notes_by_id, id_lookup


def resolve_link_target(raw_target: str, id_lookup: Dict[str, str], valid_ids: Set[str]) -> Optional[str]:
    """Resolve a raw link target string to a valid note_id."""
    clean = raw_target.strip()
    if not clean:
        return None

    # Handle formats like "[[note_id]] — Title"
    if "—" in clean:
        clean = clean.split("—")[0].strip()
    if " " in clean and "-" in clean:  # e.g. "note_id Title"
        potential_id = clean.split()[0].strip()
        if potential_id in valid_ids:
            return potential_id

    clean_fold = clean.casefold()

    # 1. Exact ID match
    if clean in valid_ids:
        return clean
    if clean_fold in id_lookup:
        return id_lookup[clean_fold]

    # 2. Prefix match on ID
    matches = [nid for nid in valid_ids if nid.startswith(clean) or nid.casefold().startswith(clean_fold)]
    if len(matches) == 1:
        return matches[0]

    return None


def extract_edges(
    notes_by_id: Dict[str, Dict[str, Any]],
    id_lookup: Dict[str, str],
    embeddings: Dict[str, np.ndarray],
) -> List[GraphEdge]:
    """Extract and deduplicate edges from wikilinks, tag overlap, embedding similarity, and PARA clusters."""
    valid_ids = sorted(list(notes_by_id.keys()))
    edge_map: Dict[Tuple[str, str], GraphEdge] = {}

    # 1. Process frontmatter links and body wikilinks
    for source_id, note in notes_by_id.items():
        body = note["content"]

        # Parse related section for explicit semantic link identification
        related_match = RELATED_SECTION_PATTERN.search(body)
        related_text = related_match.group(0) if related_match else ""

        # Extract all wikilinks from body
        body_wikilinks = WIKILINK_PATTERN.findall(body)

        # Process frontmatter links
        for raw_target in note["frontmatter_links"]:
            target_id = resolve_link_target(raw_target, id_lookup, set(valid_ids))
            if target_id and target_id != source_id and target_id in notes_by_id:
                weight = 1.0
                if source_id in embeddings and target_id in embeddings:
                    score = float(np.dot(embeddings[source_id], embeddings[target_id]))
                    weight = round(max(0.1, min(1.0, score)), 2)

                edge_key = (min(source_id, target_id), max(source_id, target_id))
                edge_map[edge_key] = GraphEdge(
                    source=source_id,
                    target=target_id,
                    type="semantic_similarity",
                    weight=weight,
                )

        # Process body wikilinks
        for raw_target in body_wikilinks:
            target_id = resolve_link_target(raw_target, id_lookup, set(valid_ids))
            if target_id and target_id != source_id and target_id in notes_by_id:
                edge_key = (min(source_id, target_id), max(source_id, target_id))

                is_related_section = raw_target in related_text
                edge_type = "semantic_similarity" if (is_related_section or target_id in note["frontmatter_links"]) else "explicit_link"

                weight = 1.0
                if source_id in embeddings and target_id in embeddings:
                    score = float(np.dot(embeddings[source_id], embeddings[target_id]))
                    weight = round(max(0.1, min(1.0, score)), 2)

                if edge_key not in edge_map or weight > edge_map[edge_key].weight:
                    edge_map[edge_key] = GraphEdge(
                        source=source_id,
                        target=target_id,
                        type=edge_type,
                        weight=weight,
                    )

    # 2. Add Tag Similarity Edges (connect notes that share tags)
    for i, id1 in enumerate(valid_ids):
        tags1 = set(t.lower() for t in notes_by_id[id1].get("tags", []))
        if not tags1:
            continue
        for id2 in valid_ids[i + 1 :]:
            tags2 = set(t.lower() for t in notes_by_id[id2].get("tags", []))
            common = tags1.intersection(tags2)
            if common:
                edge_key = (min(id1, id2), max(id1, id2))
                weight = round(min(1.0, 0.4 + 0.2 * len(common)), 2)
                if edge_key not in edge_map:
                    edge_map[edge_key] = GraphEdge(
                        source=id1,
                        target=id2,
                        type="tag_similarity",
                        weight=weight,
                    )

    # 3. Add Embedding Cosine Similarity Edges
    if embeddings:
        for i, id1 in enumerate(valid_ids):
            if id1 not in embeddings:
                continue
            for id2 in valid_ids[i + 1 :]:
                if id2 not in embeddings:
                    continue
                score = float(np.dot(embeddings[id1], embeddings[id2]))
                if score >= 0.25:
                    edge_key = (min(id1, id2), max(id1, id2))
                    weight = round(max(0.1, min(1.0, score)), 2)
                    if edge_key not in edge_map:
                        edge_map[edge_key] = GraphEdge(
                            source=id1,
                            target=id2,
                            type="embedding_similarity",
                            weight=weight,
                        )

    # 4. Connect any remaining isolated nodes to their PARA category cluster
    category_nodes: Dict[str, List[str]] = {}
    for nid, note in notes_by_id.items():
        cat = note.get("category", "Resources")
        category_nodes.setdefault(cat, []).append(nid)

    connected_nodes = set()
    for e in edge_map.values():
        connected_nodes.add(e.source)
        connected_nodes.add(e.target)

    for nid, note in notes_by_id.items():
        if nid not in connected_nodes:
            cat = note.get("category", "Resources")
            same_cat_peers = [p for p in category_nodes.get(cat, []) if p != nid]
            if same_cat_peers:
                target_peer = same_cat_peers[0]
                edge_key = (min(nid, target_peer), max(nid, target_peer))
                edge_map[edge_key] = GraphEdge(
                    source=nid,
                    target=target_peer,
                    type="para_cluster",
                    weight=0.5,
                )

    return sorted(edge_map.values(), key=lambda e: (e.source, e.target))


def build_graph(
    wiki_dir: Path = config.WIKI_DIR,
    output_path: Path = config.DATA_DIR / "graph.json",
    embeddings_path: Path = config.DATA_DIR / "embeddings.pkl",
) -> Dict[str, Any]:
    """Build knowledge graph from wiki notes and save to output_path."""
    notes_by_id, id_lookup = parse_wiki_notes(wiki_dir)
    embeddings = load_embeddings(embeddings_path)
    edges = extract_edges(notes_by_id, id_lookup, embeddings)

    # Compute node degrees for dynamic node sizing
    degrees: Dict[str, int] = {nid: 0 for nid in notes_by_id}
    for edge in edges:
        degrees[edge.source] = degrees.get(edge.source, 0) + 1
        degrees[edge.target] = degrees.get(edge.target, 0) + 1

    # Build nodes list
    nodes: List[GraphNode] = []
    for nid, note in sorted(notes_by_id.items(), key=lambda x: x[0]):
        node_size = 1 + degrees.get(nid, 0)
        nodes.append(
            GraphNode(
                id=nid,
                label=note["title"],
                category=note["category"],
                tags=note["tags"],
                summary=note["summary"],
                wiki_path=note["wiki_path"],
                size=node_size,
            )
        )

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }

    graph_data = {
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
        "metadata": metadata,
    }

    # Persist JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)

    return graph_data


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf Graph Builder (Week 3.1: Give It a Shape)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=config.DATA_DIR / "graph.json",
        help="Path to output graph JSON file (default: data/graph.json)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output messages",
    )
    args = parser.parse_args()

    try:
        graph_data = build_graph(output_path=args.output)
        if not args.quiet:
            meta = graph_data["metadata"]
            print(
                f"[SUCCESS] Built graph with {meta['node_count']} nodes and {meta['edge_count']} edges -> {args.output}"
            )
        return 0
    except Exception as exc:
        print(f"[ERROR] GRP-03: Failed to build graph: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
