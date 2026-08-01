# SecondSelf — Your Personal AI Second Brain 🧠

> **Author:** Mukesh ([@kmukessh](https://github.com/kmukessh))  
> **GitHub:** [https://github.com/kmukessh](https://github.com/kmukessh)  
> **Tech Stack:** Python 3.10+, Streamlit, Groq LLM (Llama 3.1), Sentence Transformers, vis-network

---

## 🌟 Overview

**SecondSelf** is a self-organizing personal AI Second Brain with an interactive knowledge graph and retrieval-augmented (RAG) Q&A search over captured notes and reference materials organized via the **PARA Method** (*Projects, Areas, Resources, Archives*).

---

## ✨ Features

- 📥 **Capture Inbox (`capture.py`):** One-command capture for raw notes, web URLs, and files (`.txt`, `.pdf`, `.url`).
- 🏷️ **Auto-Classification (`classify.py`):** Uses Groq Llama 3 to classify captures into PARA categories, titles, tags, and summaries with YAML frontmatter.
- 🔗 **Semantic Auto-Linking (`link.py`):** Computes local vector embeddings (`sentence-transformers`) and automatically inserts bi-directional `[[wikilinks]]` between related notes.
- 🕸️ **Knowledge Graph Builder (`build_graph.py`):** Transforms markdown notes and semantic links into an interactive force-directed graph JSON (`data/graph.json`).
- 💬 **Oracle RAG Q&A (`ask.py`):** Answers natural language queries over your knowledge base strictly using retrieved source context with exact citations.
- 🎨 **Unified Streamlit App (`app.py`):** Side-by-side interactive vis-network knowledge graph visualization and AI search bar.

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/kmukessh/second-brain.git
cd second-brain

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## 💻 Usage

### Capture Information
```bash
python capture.py --note "Meeting notes: discuss RAG architecture"
python capture.py --url "https://python.org"
python capture.py --file "path/to/document.pdf"
```

### Run Ingestion Pipeline
```bash
python pipeline.py ingest
```

### Ask Questions (RAG CLI)
```bash
python ask.py "What notes do I have about Python?"
```

### Launch Interactive App
```bash
streamlit run app.py
```

---

## 👤 Developer Profile

- **Developer:** Mukesh
- **GitHub:** [https://github.com/kmukessh](https://github.com/kmukessh)
