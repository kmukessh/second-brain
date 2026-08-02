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

import importlib
import config
import voice
importlib.reload(config)
importlib.reload(voice)

from ask import ask
from models import AskResponse
from build_graph import build_graph
from capture import capture_note, capture_url, capture_file
from classify import classify_all_unprocessed
from link import load_wiki_notes, link_notes
from voice import save_audio_file, transcribe_audio


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
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #94a3b8;
        font-size: 1.05rem;
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
        background-color: rgba(59, 130, 246, 0.2);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.5);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-areas {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.5);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-resources {
        background-color: rgba(139, 92, 246, 0.2);
        color: #c084fc;
        border: 1px solid rgba(139, 92, 246, 0.5);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-archives {
        background-color: rgba(100, 116, 139, 0.2);
        color: #94a3b8;
        border: 1px solid rgba(100, 116, 139, 0.5);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .legend-container {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 10px 16px;
        border-radius: 10px;
        margin-bottom: 12px;
    }
    .legend-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.88rem;
        color: #e2e8f0;
    }
    .dot-indicator {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 6px rgba(255,255,255,0.2);
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


def render_vis_network(graph_data: Dict[str, Any], height_px: int = 540) -> str:
    """Generate HTML string for vis-network neural brain graph."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    category_colors = {
        "Projects": "#3b82f6",   # Glowing Blue
        "Areas": "#10b981",      # Glowing Emerald
        "Resources": "#8b5cf6",  # Glowing Purple
        "Archives": "#64748b",   # Glowing Slate Gray
    }

    vis_nodes = []
    for node in nodes:
        cat = node.get("category", "Resources")
        color = category_colors.get(cat, "#3b82f6")

        tags_str = ", ".join(node.get("tags", []))
        summary_esc = html.escape(node.get("summary", ""))[:200]
        title_esc = html.escape(node.get("label", ""))
        tooltip_html = f"<b>{title_esc}</b><br/><i>Category: {cat}</i><br/>{summary_esc}<br/><br/><b>Tags:</b> {tags_str}"

        size = round((7 + min(15, (node.get("size", 1) - 1) * 2.5)) * 0.80, 2)

        vis_nodes.append(
            {
                "id": node["id"],
                "label": node["label"],
                "title": tooltip_html,
                "color": {
                    "background": color,
                    "border": "#ffffff",
                    "highlight": {"background": "#38bdf8", "border": "#ffffff"},
                    "hover": {"background": "#a855f7", "border": "#ffffff"},
                },
                "shape": "dot",
                "size": size,
                "shadow": {
                    "enabled": True,
                    "color": color,
                    "size": 8,
                    "x": 0,
                    "y": 0,
                },
                "font": {
                    "color": "#f8fafc",
                    "size": 11,
                    "face": "Inter, sans-serif",
                    "strokeWidth": 2,
                    "strokeColor": "#0b0f19",
                },
                "category": cat,
            }
        )

    vis_edges = []
    for edge in edges:
        w = edge.get("weight", 1.0)
        vis_edges.append(
            {
                "from": edge["source"],
                "to": edge["target"],
                "width": 1.5 + (w * 1.5),
                "color": {
                    "color": "rgba(99, 102, 241, 0.45)",
                    "highlight": "#38bdf8",
                    "hover": "#818cf8",
                },
                "smooth": {"type": "continuous", "roundness": 0.5},
            }
        )

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
      <style type="text/css">
        body {{
          margin: 0;
          padding: 0;
          overflow: hidden;
          background-color: transparent;
          font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }}
        .wrapper {{
          position: relative;
          width: 100%;
          height: {height_px}px;
        }}
        #network {{
          width: 100%;
          height: 100%;
          background: radial-gradient(circle at center, #1e293b 0%, #0b0f19 100%);
          border-radius: 14px;
          border: 1px solid rgba(99, 102, 241, 0.25);
          box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.6), 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div id="network"></div>
      </div>
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
            selectionWidth: 3
          }},
          physics: {{
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {{
              gravitationalConstant: -35,
              centralGravity: 0.015,
              springLength: 95,
              springConstant: 0.08,
              damping: 0.4,
              avoidOverlap: 0.6
            }},
            stabilization: {{ iterations: 200 }}
          }},
          interaction: {{
            hover: true,
            tooltipDelay: 80,
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
            ["📝 Note", "🎙️ Voice", "🔗 Web Link", "📁 File"],
            horizontal=True,
            key="cap_type_radio",
        )

        if cap_type == "📝 Note":
            note_input = st.text_area("Note Text:", placeholder="Type a note, idea, or meeting summary...", height=90)
            if st.button("📥 Save & Process Note", use_container_width=True):
                if not note_input.strip():
                    st.error("Note content cannot be empty!")
                else:
                    try:
                        with st.spinner("Capturing & classifying note..."):
                            capture_note(note_input)
                            process_new_captures()
                        st.toast("✨ Note captured, classified & graph updated!", icon="🎉")
                        st.rerun()
                    except ValueError as exc:
                        st.warning(f"⚠️ {exc}")

        elif cap_type == "🎙️ Voice":
            st.markdown("##### 🎙️ Voice Note Capture")

            col_v1, col_v2 = st.columns([3, 1])
            with col_v1:
                st.caption("Click the mic to Record live voice:")
            with col_v2:
                if st.button("🔄", help="Reset recording & transcript", use_container_width=True):
                    st.session_state["voice_transcript"] = ""
                    st.session_state["recorded_audio_bytes"] = None
                    st.rerun()

            # 1. Live Microphone Recorder
            st.markdown("**1. Live Microphone Recording:**")
            raw_voice_bytes = None
            try:
                from audio_recorder_streamlit import audio_recorder

                recorded_data = audio_recorder(
                    text="Record Live Voice",
                    recording_color="#ef4444",
                    neutral_color="#3b82f6",
                    icon_name="microphone",
                    icon_size="2x",
                    key="live_audio_rec_key",
                )

                if isinstance(recorded_data, bytes) and len(recorded_data) > 0:
                    raw_voice_bytes = recorded_data
                elif isinstance(recorded_data, dict) and recorded_data.get("bytes"):
                    raw_voice_bytes = recorded_data["bytes"]
            except Exception as exc:
                st.warning(f"Live mic notice: {exc}")

            # Process & store live recording
            if raw_voice_bytes and st.session_state.get("recorded_audio_bytes") != raw_voice_bytes:
                st.session_state["recorded_audio_bytes"] = raw_voice_bytes
                try:
                    with st.spinner("Transcribing your voice with Whisper AI..."):
                        audio_path = save_audio_file(raw_voice_bytes, extension=".wav")
                        res = transcribe_audio(audio_path)
                        text_res = res.get("text", "")
                        if res.get("status") == "success" and text_res:
                            st.session_state["voice_transcript"] = text_res
                            st.toast("🎉 Live voice recorded & transcribed!", icon="🎙️")
                        elif res.get("status") == "success":
                            st.warning("⚠️ Recording saved! No clear speech detected.")
                        else:
                            st.error(f"Transcription error: {res.get('status')}")
                except Exception as exc:
                    st.error(f"Failed to save/transcribe recording: {exc}")

            # 2. Audio File Upload Option (Alternative)
            st.markdown("**2. Or Upload Audio File:**")
            uploaded_audio = st.file_uploader(
                "Upload Voice Memo / Audio File:",
                type=["wav", "mp3", "m4a", "ogg", "webm"],
                key="uploaded_voice_file",
            )
            if uploaded_audio is not None:
                if st.button("✨ Transcribe Uploaded Audio", use_container_width=True):
                    with st.spinner("Transcribing audio file with Whisper AI..."):
                        try:
                            audio_bytes_file = uploaded_audio.getvalue()
                            st.session_state["recorded_audio_bytes"] = audio_bytes_file
                            audio_path = save_audio_file(uploaded_audio)
                            res = transcribe_audio(audio_path)
                            text_res = res.get("text", "")
                            st.session_state["voice_transcript"] = text_res
                            if res.get("status") == "success":
                                st.toast("🎉 Audio file transcribed successfully!", icon="🎙️")
                            else:
                                st.error(f"Transcription status: {res.get('status')}")
                        except Exception as exc:
                            st.error(f"Failed to transcribe audio file: {exc}")

            # 3. Audio Playback Player (Hear your recording!)
            current_audio = st.session_state.get("recorded_audio_bytes")
            if current_audio and isinstance(current_audio, bytes):
                import base64

                st.markdown("##### 🔊 Hear Your Recording:")
                b64_audio = base64.b64encode(current_audio).decode()
                st.markdown(
                    f'<audio controls controlsList="nodownload" style="width: 100%; border-radius: 8px; margin: 8px 0;">'
                    f'<source src="data:audio/wav;base64,{b64_audio}" type="audio/wav">'
                    f'Your browser does not support audio playing.'
                    f'</audio>',
                    unsafe_allow_html=True,
                )

            # 4. Review & Edit Transcript
            current_transcript = st.session_state.get("voice_transcript", "")
            edited_transcript = st.text_area(
                "Review & Edit Transcript:",
                value=current_transcript,
                placeholder="Transcribed voice text will appear here. Edit or add details before saving...",
                height=110,
            )

            if st.button("📥 Save & Process Voice Note", use_container_width=True):
                if not edited_transcript.strip():
                    st.error("Voice note content cannot be empty!")
                else:
                    try:
                        with st.spinner("Capturing & classifying voice note..."):
                            capture_note(edited_transcript)
                            process_new_captures()
                        st.session_state["voice_transcript"] = ""
                        st.session_state["recorded_audio_bytes"] = None
                        st.toast("✨ Voice note captured, classified & graph updated!", icon="🎉")
                        st.rerun()
                    except ValueError as exc:
                        st.warning(f"⚠️ {exc}")

        elif cap_type == "🔗 Web Link":
            url_input = st.text_input("URL Link:", placeholder="https://example.com/article")
            if st.button("📥 Save & Process Link", use_container_width=True):
                if not url_input.strip():
                    st.error("URL cannot be empty!")
                else:
                    try:
                        with st.spinner("Fetching URL preview & classifying..."):
                            capture_url(url_input)
                            process_new_captures()
                        st.toast("✨ URL captured, classified & graph updated!", icon="🎉")
                        st.rerun()
                    except ValueError as exc:
                        st.warning(f"⚠️ {exc}")

        elif cap_type == "📁 File":
            uploaded_file = st.file_uploader("Upload File:", type=["txt", "pdf", "md"])
            if st.button("📥 Save & Process File", use_container_width=True):
                if uploaded_file is None:
                    st.error("Please select a file to upload!")
                else:
                    try:
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
                    except ValueError as exc:
                        st.warning(f"⚠️ {exc}")

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

    # Main Landscape Layout
    # Section 1: Ask Your Brain (RAG Search) at the top
    st.subheader("💬 Ask Your Brain (RAG Search)")

    if "recent_questions" not in st.session_state:
        st.session_state["recent_questions"] = []

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
        "Search or ask a question across your SecondSelf knowledge base:",
        value=query_input,
        placeholder="e.g. What notes do I have about vector embeddings?",
    )

    if user_query:
        clean_q = user_query.strip()
        q_lower = clean_q.lower()

        # Check if user is asking about previous questions / history
        history_phrases = [
            "previous", "prev", "last question", "past question", "asked",
            "search history", "what did i ask", "my question", "queries", "history"
        ]
        is_history_query = any(p in q_lower for p in history_phrases)

        current_history = st.session_state.get("recent_questions", [])

        if is_history_query:
            if current_history:
                history_formatted = "\n".join(f"**{i+1}.** {q}" for i, q in enumerate(current_history))
                ans_text = f"**Here are the questions you previously asked in this session:**\n\n{history_formatted}"
            else:
                ans_text = "You haven't asked any previous questions in this session yet."
            response = AskResponse(answer=ans_text, sources=[])
        else:
            # Save new question to history (Keep last 3 questions)
            if clean_q and clean_q not in current_history:
                st.session_state["recent_questions"].insert(0, clean_q)
                st.session_state["recent_questions"] = st.session_state["recent_questions"][:3]

            with st.spinner("Searching & synthesizing answer from your SecondSelf Second Brain..."):
                response = ask(user_query)

        st.markdown("### 💡 Answer")
        st.markdown(
            f'<div class="card">{response.answer}</div>',
            unsafe_allow_html=True,
        )

        # Always show Last 3 Recent Questions History under the answer if available
        all_history = st.session_state.get("recent_questions", [])[:3]
        if all_history:
            with st.expander("📜 Last 3 Previously Asked Questions", expanded=is_history_query):
                for idx, q in enumerate(all_history, 1):
                    st.write(f"**{idx}.** {q}")

        if response.sources:
            st.markdown("### 📚 Source Citations")
            for src in response.sources:
                pct = int(src.score * 100)
                with st.expander(f"📄 {src.title} ({pct}% match)"):
                    st.write(f"**Path:** `{src.wiki_path}`")
                    st.write(f"**Relevance Score:** `{src.score:.2%}`")
                    st.write(f"**Note ID:** `{src.id}`")

    st.divider()

    # Section 2: Landscape Knowledge Graph & Vision Legend below Search
    st.subheader("Knowledge Graph")

    # Color Legend Header in Streamlit UI
    st.markdown(
        """
        <div class="legend-container">
            <span style="font-weight:700; color:#cbd5e1; margin-right:8px;">Vision:</span>
            <div class="legend-item"><span class="dot-indicator" style="background-color:#3b82f6;"></span><span>Projects</span></div>
            <div class="legend-item"><span class="dot-indicator" style="background-color:#10b981;"></span><span>Areas</span></div>
            <div class="legend-item"><span class="dot-indicator" style="background-color:#8b5cf6;"></span><span>Resources</span></div>
            <div class="legend-item"><span class="dot-indicator" style="background-color:#64748b;"></span><span>Archives</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not nodes:
        st.info("No notes captured yet. Run `python capture.py` and `python classify.py --all` to get started!")
    else:
        graph_html = render_vis_network(graph_data, height_px=540)
        components.html(graph_html, height=560)


if __name__ == "__main__":
    main()
