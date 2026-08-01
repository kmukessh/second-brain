from pathlib import Path
import os
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Root directory configuration
ROOT = Path(__file__).parent.resolve()
RAW_DIR = ROOT / "raw"
WIKI_DIR = ROOT / "wiki"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
LIB_DIR = ROOT / "lib"
DOCS_DIR = ROOT / "docs"
STATIC_DIR = ROOT / "static"

# Ensure directory scaffold exists
for directory in [RAW_DIR, WIKI_DIR, DATA_DIR, LOGS_DIR, LIB_DIR, DOCS_DIR, STATIC_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

for para in ["Projects", "Areas", "Resources", "Archives"]:
    (WIKI_DIR / para).mkdir(parents=True, exist_ok=True)

def _get_config(key: str, default: Any = "") -> Any:
    """Retrieve configuration from st.secrets if running in Streamlit, falling back to os.getenv."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)

# AI & LLM Settings
GROQ_API_KEY = _get_config("GROQ_API_KEY", "")
GROQ_MODEL = _get_config("GROQ_MODEL", "llama-3.1-8b-instant")

# Embedding & Similarity Settings
EMBEDDING_MODEL = _get_config("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SIMILARITY_THRESHOLD = float(_get_config("SIMILARITY_THRESHOLD", "0.75"))
RAG_TOP_K = int(_get_config("RAG_TOP_K", "5"))
MAX_LINKS_PER_NOTE = int(_get_config("MAX_LINKS_PER_NOTE", "5"))
MAX_FILE_SIZE_MB = int(_get_config("MAX_FILE_SIZE_MB", "25"))
