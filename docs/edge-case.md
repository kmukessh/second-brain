# SecondSelf — Edge Cases & Corner Scenarios

> **Project:** SecondSelf — Your Personal AI Second Brain  
> **References:** `architecture.md`, `Implementation-plan.md`  
> **Purpose:** Comprehensive matrix of edge cases, failure modes, corner scenarios, and mitigation strategies across all modules and build phases.

---

## 1. Executive Summary & Guardrail Strategy

Building a self-organizing knowledge graph with LLMs and local vector embeddings introduces non-deterministic inputs, ephemeral environments, file-system edge cases, and API limits. This document maps every potential breakdown in SecondSelf's pipeline—from capture to cloud deployment—providing concrete detection, handling, and fallback protocols.

---

## 2. Component-Wise Edge Case Matrix

### 2.1 Phase 1: Capture Pipeline (`capture.py`) & Inbox (`raw/`)

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **CAP-01** | Input Validation | Empty text capture (`python capture.py --note ""`) | Zero-byte raw file created, breaking downstream extraction. | Reject command with clear CLI error message. Do not write to `raw/`. |
| **CAP-02** | File System | Non-existent or inaccessible file path (`--file "./missing.pdf"`) | `FileNotFoundError` or permission exception crash. | Validate file existence, readability, and size before copying. |
| **CAP-03** | Network / HTTP | URL fetch fails (404, 500, DNS failure, timeout, SSL error) | Script hangs or crashes on `requests.get()`. | Set 10s connection timeout; catch `requests.RequestException`; fall back to saving URL metadata only with `.txt` fallback note. |
| **CAP-04** | Web Scraping | URL content is JavaScript-rendered SPA or paywalled/login-protected | Extracted content is empty or contains "Enable JavaScript" boilerplate. | Store raw HTML/title; fallback to extracting HTML meta tags (`<meta name="description">`). Mark summary as limited. |
| **CAP-05** | File Handling | Extremely large PDF/File (>50MB) | High disk usage, high memory during hashing or parsing. | Enforce file size limit (`MAX_FILE_SIZE = 25MB`); warn user if exceeded. |
| **CAP-06** | OS & Encoding | Filenames or text content with special characters, emojis, or non-UTF-8 encodings | Windows file path errors or `UnicodeDecodeError`. | Enforce `utf-8` with `errors="replace"`; sanitize filenames to ASCII alphanumeric + hyphens. |
| **CAP-07** | Concurrency | Duplicate capture of exact same text or file in rapid succession | Duplicate raw files polluting `wiki/`. | Compute SHA-256 hash in `.meta.json`; check existing `raw/` hashes before saving. |
| **CAP-08** | Windows Paths | Deep folder paths exceeding Windows `MAX_PATH` (260 chars) | `OSError: [Errno 2] No such file or directory`. | Keep raw filenames short using timestamp + truncated 8-character UUID (`YYYYMMDD_HHMMSS_{short_id}`). |

---

### 2.2 Phase 2: Auto-Classification Pipeline (`classify.py`)

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **CLS-01** | LLM API | Groq API rate limit reached (`HTTP 429`) or quota exhausted | Classification fails; raw capture remains unparsed. | Exponential backoff retry (3 attempts). If persistent, skip note, log error, and continue batch. |
| **CLS-02** | LLM API | Groq API server down (`HTTP 500/503`) or network offline | Script crashes mid-batch execution. | Wrap API calls in `try/except`. Log failure in `logs/secondself.log`. Preserve `processed: false` state for retry. |
| **CLS-03** | LLM Output | LLM returns invalid JSON or extra markdown backticks | `json.JSONDecodeError` when parsing response. | Strip ```json wrappers using regex; use pydantic/json schema repair; fall back to regex extraction for title/tags/category. |
| **CLS-04** | LLM Output | LLM assigns invalid PARA category (e.g., `"Work"` instead of `"Projects"`) | Note saved in unrecognized directory, breaking frontmatter schema. | Enforce strict enum validation (`Projects`, `Areas`, `Resources`, `Archives`). Fallback to `Resources` if invalid. |
| **CLS-05** | PDF Processing | Scanned PDF (image-only, no selectable text) or password-protected PDF | `pypdf` returns empty text or raises `PdfReadError`. | Catch `PdfReadError`; save frontmatter with `extraction_status: "scanned_pdf_text_missing"`; summarize filename/metadata instead. |
| **CLS-06** | Text Length | Input capture exceeds LLM context token window | LLM truncates response or rejects prompt. | Truncate raw input text to first 4,000 words prior to sending to LLM. |
| **CLS-07** | Filename | Two raw notes generate identical slugified titles (e.g., "RAG Architecture") | File overwrite in `wiki/` directory. | Append `-{short_id}` to wiki markdown filename if `wiki/{category}/{slug}.md` already exists. |

---

### 2.3 Phase 3: Auto-Linking Pipeline (`link.py`)

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **LNK-01** | Sparse Data | Only 0 or 1 note exists in `wiki/` | Cosine similarity matrix calculation breaks or returns empty. | Check if `len(wiki_notes) < 2`; log skip message gracefully without modifying files. |
| **LNK-02** | Low Similarity | No other notes meet `SIMILARITY_THRESHOLD` (e.g. 0.75) | Note left without related links. | Valid operational state. Leave `links: []` empty in frontmatter and skip `## Related` section. |
| **LNK-03** | Over-Clustering | Dense topic generates >20 similar notes | Note frontmatter flooded with dozens of links. | Enforce `MAX_LINKS_PER_NOTE = 5`, sorting by top cosine similarity scores. |
| **LNK-04** | Self-Linking | A note vector matches itself with cosine similarity `1.0` | Note links to itself in `## Related`. | Filter out `source_note_id == target_note_id` during similarity matching. |
| **LNK-05** | Index Corruption | `data/embeddings.pkl` missing, corrupted, or incompatible with updated model | `pickle.UnpicklingError` or vector dimension mismatch. | Delete corrupt `.pkl` file and regenerate full embeddings index from scratch from `wiki/` files. |
| **LNK-06** | Broken Links | Target note deleted or moved after link was established | `[[note-id]]` points to non-existent file. | Validate target note existence when building graph; clean up dangling links during re-indexing. |

---

### 2.4 Phase 4 & 5A: Graph Builder (`build_graph.py`) & UI (`app.py` / vis-network)

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **GRP-01** | Data State | Empty knowledge base (0 notes in `wiki/`) | `data/graph.json` missing or empty (`{"nodes": [], "edges": []}`). | Render an informative empty state UI in Streamlit: "No notes captured yet. Run capture.py to begin." |
| **GRP-02** | Graph Topology | Disconnected graph (isolated nodes with 0 edges) | Nodes float independently in graph visualization. | Supported by design. vis-network physics handles isolated nodes naturally. |
| **GRP-03** | Graph Topology | Extremely dense graph (1,000+ edges) | vis-network force-directed physics engine stutters, causing browser lag. | Disable active physics after stabilization (`physics: { barnesHut: { avoidOverlap: 0.5 }, solver: 'barnesHut' }`); cap visible edges. |
| **GRP-04** | JSON Serialization | Datetime or UUID objects present in node metadata | `TypeError: Object of type datetime is not JSON serializable`. | Cast all timestamps to ISO-8601 strings and UUIDs to string before saving `graph.json`. |
| **GRP-05** | UI Interaction | User clicks node with special characters or long summary | Tooltip breaks HTML layout or JavaScript syntax errors in Streamlit component. | Escape HTML entities in summaries (`html.escape()`); truncate tooltips to 200 characters. |

---

### 2.5 Phase 5B & 7: RAG Q&A (`ask.py`) & Local Validation

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **RAG-01** | Hallucination | User asks question about topic completely absent from `wiki/` | LLM fabricates facts not present in notes. | Strict system prompt instruction: *"Answer strictly using only the provided sources. If answer cannot be deduced, respond: 'I don't have information on this in your Second Brain.'"* |
| **RAG-02** | Relevance | Top-k retrieved notes have very low similarity scores (<0.30) | Low-quality, irrelevant context sent to LLM. | Enforce minimum similarity filter for RAG retrieval (`RAG_MIN_SIMILARITY = 0.40`). If no context passes, return "No relevant notes found." |
| **RAG-03** | Prompt Injection | User enters prompt attempting to override RAG instructions (e.g. `"Ignore previous instructions..."`) | Agent leaks system prompt or ignores source boundaries. | Sanitize query inputs; isolate context within XML blocks (`<context>{notes}</context>`). |
| **RAG-04** | Missing Meta | Retrieved note file missing `title` or `summary` frontmatter | UI source citations fail or display `null`. | Fallback source citation title to note filename or ID if frontmatter title is missing. |
| **RAG-05** | Performance | High latency on embedding generation + Groq API call (>15s) | Streamlit UI appears frozen. | Add `st.spinner("Thinking & searching your second brain...")` and cache query embeddings when possible. |

---

### 2.6 Phase 8 & 9: Cloud Deployment & Ephemeral Storage (Streamlit Cloud)

| ID | Category | Scenario / Edge Case | Expected Impact | Mitigation / Handling Strategy |
|---|---|---|---|---|
| **DEP-01** | Ephemeral FS | User attempts capture on deployed Streamlit Cloud app | Files saved to ephemeral disk disappear on app reboot. | Pre-build and commit static `wiki/`, `data/embeddings.pkl`, and `data/graph.json` to GitHub repo. Disable write actions in Cloud UI or display "Read-only Demo Mode" banner. |
| **DEP-02** | Environment | `GROQ_API_KEY` missing from Streamlit Cloud Secrets | App crashes on first RAG query with `KeyError`. | Add startup check in `app.py`: `if not GROQ_API_KEY: st.error("GROQ_API_KEY environment variable missing.")`. |
| **DEP-03** | Memory / Build | `sentence-transformers` PyTorch dependency memory limit on free cloud tier | Deployment build timeout or Out Of Memory (OOM) crash. | Use lightweight model `all-MiniLM-L6-v2`; use CPU-only PyTorch build in `requirements.txt`. |
| **DEP-04** | Assets | Missing static files or relative path mismatches on Linux container | `FileNotFoundError` for `data/graph.json`. | Use `Path(__file__).parent` in `config.py` for absolute path resolution across OS environments. |

---

## 3. Cross-Cutting Failure Modes & Recovery Matrix

| Scenario | Symptom | Diagnostic Step | Recovery Action |
|---|---|---|---|
| **Corrupted Frontmatter** | `yaml.YAMLError` during `classify.py` or `build_graph.py` | Run `python -c "import frontmatter; frontmatter.load('wiki/path.md')"` | Move corrupt note to `logs/corrupt/`, fix YAML manually, or re-run `classify.py --force`. |
| **API Key Quota Exhausted** | `groq.RateLimitError` across all RAG queries | Inspect `logs/secondself.log` for HTTP 429 status code | Swap API key in `.env` or implement mock fallback response for demo. |
| **Pickle Model Mismatch** | Vector dimension error in `sentence-transformers` | Compare vector dimensions: `len(vec) != model.get_sentence_embedding_dimension()` | Delete `data/embeddings.pkl` and re-run `python link.py --all`. |
| **Streamlit State Reset** | UI graph disappears on sidebar interaction | Check `st.session_state` keys in `app.py` | Store graph JSON and selected node ID in `st.session_state`. |

---

## 4. Test Verification & Edge Case Guardrail Checklist

- [ ] **Empty Input Test:** Verify `python capture.py --note ""` is rejected cleanly.
- [ ] **Scanned PDF Test:** Capture an image-only PDF and confirm no pipeline crashes.
- [ ] **Invalid API Key Test:** Run `ask.py` with invalid key and verify user-friendly error UI.
- [ ] **Zero Notes Test:** Delete `wiki/` content temporarily and verify `app.py` renders empty state without 500 error.
- [ ] **Out of Domain Query Test:** Ask `ask.py` about "quantum gravity rocket engines" and verify response is "I don't know" rather than a hallucination.
- [ ] **Cross-Platform Path Test:** Run pipeline on Windows and verify forward slashes in `graph.json` relative paths.
- [ ] **JSON Repair Test:** Feed LLM response with ```json markdown blocks into `classify.py` parser.

---
