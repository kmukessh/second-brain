from pathlib import Path
import os
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

# AI & LLM Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

# Embedding & Similarity Settings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
MAX_LINKS_PER_NOTE = int(os.getenv("MAX_LINKS_PER_NOTE", "5"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
