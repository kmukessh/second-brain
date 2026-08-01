#!/usr/bin/env python3
"""SecondSelf CLI Orchestrator (pipeline.py)

Usage:
  python pipeline.py ingest   # Classify all unprocessed captures -> Auto-link -> Rebuild Graph
  python pipeline.py graph    # Rebuild Knowledge Graph JSON
  python pipeline.py ask "question text"  # Perform RAG query
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def run_ingest() -> int:
    """Run classify -> link -> build_graph in sequence."""
    print("=== Step 1/3: Classifying Raw Captures ===")
    res_cls = subprocess.run([sys.executable, "classify.py", "--all"])
    if res_cls.returncode != 0:
        print("[ERROR] Classification failed.")
        return res_cls.returncode

    print("\n=== Step 2/3: Semantic Auto-Linking ===")
    res_lnk = subprocess.run([sys.executable, "link.py", "--all"])
    if res_lnk.returncode != 0:
        print("[ERROR] Auto-linking failed.")
        return res_lnk.returncode

    print("\n=== Step 3/3: Rebuilding Knowledge Graph ===")
    res_grp = subprocess.run([sys.executable, "build_graph.py"])
    if res_grp.returncode != 0:
        print("[ERROR] Graph building failed.")
        return res_grp.returncode

    print("\n[SUCCESS] Ingestion pipeline complete! Graph updated.")
    return 0


def run_graph() -> int:
    """Rebuild knowledge graph JSON."""
    res = subprocess.run([sys.executable, "build_graph.py"])
    return res.returncode


def run_ask(question: str) -> int:
    """Run ask.py RAG query."""
    res = subprocess.run([sys.executable, "ask.py", question])
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf Pipeline Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ingest", help="Classify raw captures, build semantic links, and update graph")
    subparsers.add_parser("graph", help="Rebuild data/graph.json from wiki notes")

    ask_parser = subparsers.add_parser("ask", help="Query your Second Brain using RAG Q&A")
    ask_parser.add_argument("question", help="Question text")

    args = parser.parse_args()

    if args.command == "ingest":
        return run_ingest()
    elif args.command == "graph":
        return run_graph()
    elif args.command == "ask":
        return run_ask(args.question)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
