#!/usr/bin/env python3
"""SecondSelf Streamlit App (Weeks 3.2 + 4)

Unified UI providing:
1. 🧠 Interactive force-directed Knowledge Graph visualization (vis-network)
2. 💬 RAG Q&A Search bar over personal wiki notes
3. 📊 Sidebar stats, PARA breakdown, and Rebuild Graph controls
"""

import html
import json
from pathlib import Path
from typing import Any, Dict

import streamlit as st
import streamlit.components.v1 as components

import config
from ask import ask
from build_graph import build_graph
from capture import capture_note, capture_url, capture_file
from classify import classify_all_unprocessed
from link import load_wiki_notes, link_notes


def process_new_captures():
    """Classify, link, and rebuild graph for all new captures."""
    classify_all_unprocessed()
    notes = load_wiki_notes()
    if notes:
        link_notes(notes)
    build_graph()


# Page configuration
st.set_page_config(
    page_title="SecondSelf — AI Second Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich aesthetics
st.markdown(
    """
    <style>
    /* Dark glassmorphism theme */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #94a3b8;
        font-size: 1.0rem;
        margin-bottom: 1.5rem;
    }
    .card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(8px);
        line-height: 1.6;
    }
    .badge-projects {
        background-color: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-areas {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-resources {
        background-color: rgba(139, 92, 246, 0.2);
        color: #c084fc;
        border: 1px solid rgba(139, 92, 246, 0.4);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-archives {
        background-color: rgba(107, 114, 128, 0.2);
        color: #9ca3af;
        border: 1px solid rgba(107, 114, 128, 0.4);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_graph_data() -> Dict[str, Any]:
    """Load data/graph.json or generate it if missing."""
    graph_file = config.DATA_DIR / "graph.json"
    if not graph_file.exists():
        try:
            return build_graph()
        except Exception as exc:
            st.error(f"Failed to build graph JSON: {exc}")
            return {"nodes": [], "edges": [], "metadata": {"node_count": 0, "edge_count": 0}}
    try:
        with graph_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return build_graph()


def render_vis_network(graph_data: Dict[str, Any], height_px: int = 580) -> str:
    """Generate HTML string for vis-network force-directed graph."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    category_colors = {
        "Projects": "#ef4444",
        "Areas": "#10b981",
        "Resources": "#8b5cf6",
        "Archives": "#6b7280",
    }

    vis_nodes = []
    for node in nodes:
        cat = node.get("category", "Resources")
        color = category_colors.get(cat, "#3b82f6")

        tags_str = ", ".join(node.get("tags", []))
        summary_esc = html.escape(node.get("summary", ""))[:200]
        title_esc = html.escape(node.get("label", ""))
        tooltip_html = f"<b>{title_esc}</b><br/><i>{cat}</i><br/>{summary_esc}<br/><br/><b>Tags:</b> {tags_str}"

        vis_nodes.append(
            {
                "id": node["id"],
                "label": node["label"],
                "title": tooltip_html,
                "color": {
                    "background": color,
                    "border": "#ffffff",
                    "highlight": {"background": "#f59e0b", "border": "#ffffff"},
                },
                "shape": "dot",
                "size": 12 + min(30, (node.get("size", 1) - 1) * 6),
                "font": {"color": "#f8fafc", "size": 14, "face": "Inter, sans-serif"},
                "category": cat,
                "summary": node.get("summary", ""),
                "wiki_path": node.get("wiki_path", ""),
            }
        )

    vis_edges = []
    for edge in edges:
        vis_edges.append(
            {
                "from": edge["source"],
                "to": edge["target"],
                "value": edge.get("weight", 1.0),
                "color": {"color": "#475569", "highlight": "#6366f1"},
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
            }
        )

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <style type="text/css">
        #network {{
          width: 100%;
          height: {height_px}px;
          background-color: #1e293b;
          border-radius: 12px;
          border: 1px solid #334155;
        }}
      </style>
    </head>
    <body>
      <div id="network"></div>
      <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(vis_nodes)});
        var edges = new vis.DataSet({json.dumps(vis_edges)});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
          nodes: {{
            borderWidth: 2,
            shadow: true
          }},
          edges: {{
            width: 1.5,
            smooth: {{ type: 'continuous' }}
          }},
          physics: {{
            solver: 'barnesHut',
            barnesHut: {{
              gravitationalConstant: -3000,
              centralGravity: 0.3,
              springLength: 95,
              springConstant: 0.04,
              damping: 0.09,
              avoidOverlap: 0.5
            }},
            stabilization: {{ iterations: 150 }}
          }},
          interaction: {{
            hover: true,
            tooltipDelay: 100,
            zoomView: true,
            dragView: true
          }}
        }};
        var network = new vis.Network(container, data, options);
      </script>
    </body>
    </html>
    """
    return html_code


def main():
    st.markdown('<div class="main-header">🧠 SecondSelf</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Your Self-Organizing AI Knowledge Graph & Retrieval Assistant • Built by <a href="https://github.com/kmukessh" target="_blank" style="color:#c084fc; text-decoration:none; font-weight:600;">Mukesh</a></div>',
        unsafe_allow_html=True,
    )

    if not config.GROQ_API_KEY:
        st.warning("⚠️ `GROQ_API_KEY` is not set. Add it to your `.env` locally or to **Streamlit Secrets** (`GROQ_API_KEY`) on Streamlit Cloud for AI RAG search & auto-classification.")

    graph_data = load_graph_data()
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    # Sidebar
    with st.sidebar:
        st.header("⚡ Quick Capture")
        cap_type = st.radio(
            "Select Format:",
            ["📝 Note", "🔗 Web Link", "📁 File"],
            horizontal=True,
            key="cap_type_radio",
        )

        if cap_type == "📝 Note":
            note_input = st.text_area("Note Text:", placeholder="Type a note, idea, or meeting summary...", height=90)
            if st.button("📥 Save & Process Note", use_container_width=True):
                if not note_input.strip():
                    st.error("Note content cannot be empty!")
                else:
                    with st.spinner("Capturing & classifying note..."):
                        capture_note(note_input)
                        process_new_captures()
                    st.toast("✨ Note captured, classified & graph updated!", icon="🎉")
                    st.rerun()

        elif cap_type == "🔗 Web Link":
            url_input = st.text_input("URL Link:", placeholder="https://example.com/article")
            if st.button("📥 Save & Process Link", use_container_width=True):
                if not url_input.strip():
                    st.error("URL cannot be empty!")
                else:
                    with st.spinner("Fetching URL preview & classifying..."):
                        capture_url(url_input)
                        process_new_captures()
                    st.toast("✨ URL captured, classified & graph updated!", icon="🎉")
                    st.rerun()

        elif cap_type == "📁 File":
            uploaded_file = st.file_uploader("Upload File:", type=["txt", "pdf", "md"])
            if st.button("📥 Save & Process File", use_container_width=True):
                if uploaded_file is None:
                    st.error("Please select a file to upload!")
                else:
                    with st.spinner("Saving file & classifying..."):
                        temp_dir = config.RAW_DIR / "temp"
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        temp_path = temp_dir / uploaded_file.name
                        temp_path.write_bytes(uploaded_file.getbuffer())

                        capture_file(str(temp_path))
                        if temp_path.exists():
                            temp_path.unlink()

                        process_new_captures()
                    st.toast("✨ File captured, classified & graph updated!", icon="🎉")
                    st.rerun()

        st.divider()

        st.header("⚙️ Brain Control")
        if st.button("🔄 Rebuild Graph", use_container_width=True):
            with st.spinner("Rebuilding knowledge graph..."):
                build_graph()
                st.success("Graph rebuilt!")
                st.rerun()

        st.divider()
        st.header("📊 Knowledge Stats")
        col_s1, col_s2 = st.columns(2)
        col_s1.metric("Notes", len(nodes))
        col_s2.metric("Links", len(edges))

        st.markdown("#### PARA Breakdown")
        para_counts = {"Projects": 0, "Areas": 0, "Resources": 0, "Archives": 0}
        for n in nodes:
            cat = n.get("category", "Resources")
            if cat in para_counts:
                para_counts[cat] += 1
            else:
                para_counts["Resources"] += 1

        for cat, count in para_counts.items():
            badge_class = f"badge-{cat.lower()}"
            st.markdown(
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">'
                f'<span class="{badge_class}">{cat}</span>'
                f'<span style="font-weight:600; color:#cbd5e1;">{count}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown(
            '<div style="text-align: center; color: #94a3b8; font-size: 0.85rem;">'
            'Built with ❤️ by <b>Mukesh</b><br/>'
            '<a href="https://github.com/kmukessh" target="_blank" style="color: #818cf8; text-decoration: none; font-weight: 600;">🔗 github.com/kmukessh</a>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Main Grid Layout
    left_col, right_col = st.columns([1.2, 1], gap="medium")

    with left_col:
        st.subheader("🕸️ Knowledge Graph")
        if not nodes:
            st.info("No notes captured yet. Run `python capture.py` and `python classify.py --all` to get started!")
        else:
            graph_html = render_vis_network(graph_data)
            components.html(graph_html, height=600)

    with right_col:
        st.subheader("💬 Ask Your Brain")

        st.caption("Quick Queries:")
        q_cols = st.columns(3)
        query_input = ""
        if q_cols[0].button("🚀 Projects", use_container_width=True):
            query_input = "What projects am I currently working on?"
        if q_cols[1].button("🤖 RAG Notes", use_container_width=True):
            query_input = "What did I capture about RAG architecture?"
        if q_cols[2].button("🐍 Python", use_container_width=True):
            query_input = "What resources do I have about Python?"

        user_query = st.text_input(
            "Search or ask a question:",
            value=query_input,
            placeholder="e.g. What notes do I have about vector embeddings?",
        )

        if user_query:
            with st.spinner("Searching & synthesizing answer from your Second Brain..."):
                response = ask(user_query)

            st.markdown("### 💡 Answer")
            st.markdown(
                f'<div class="card">{response.answer}</div>',
                unsafe_allow_html=True,
            )

            if response.sources:
                st.markdown("### 📚 Source Citations")
                for src in response.sources:
                    pct = int(src.score * 100)
                    with st.expander(f"📄 {src.title} ({pct}% match)"):
                        st.write(f"**Path:** `{src.wiki_path}`")
                        st.write(f"**Relevance Score:** `{src.score:.2%}`")
                        st.write(f"**Note ID:** `{src.id}`")


if __name__ == "__main__":
    main()
