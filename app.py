#!/usr/bin/env python3

import html
import json
from pathlib import Path
from typing import Any, Dict

import streamlit as st
import streamlit.components.v1 as components

import importlib
import config
import voice
import models
import ask
import calendar_service
importlib.reload(config)
importlib.reload(voice)
importlib.reload(models)
importlib.reload(ask)
importlib.reload(calendar_service)

from ask import ask
from models import AskResponse, CalendarEvent
from build_graph import build_graph
from capture import capture_note, capture_url, capture_file
from classify import classify_all_unprocessed
from link import load_wiki_notes, link_notes
from voice import save_audio_file, transcribe_audio
from calendar_service import (
    create_event,
    delete_event,
    get_today_events,
    get_upcoming_events,
    parse_and_execute_calendar_request,
    is_schedulable_event,
    format_google_calendar_template_url,
    parse_datetime_string,
)

import frontmatter
from google_services import google_service_manager





def get_all_calendar_events_and_meetings():
    events = []
    seen_summaries = set()

    # Pre-build lookup of wiki notes by calendar_event_id and title
    wiki_notes_map = {}
    for wiki_file in config.WIKI_DIR.glob("*/*.md"):
        if wiki_file.name.startswith("."):
            continue
        try:
            post = frontmatter.load(wiki_file)
            rel_p = str(wiki_file.relative_to(config.ROOT))
            t = str(post.get("title", wiki_file.stem)).strip()
            cid = post.get("calendar_event_id")
            if cid:
                wiki_notes_map[str(cid)] = rel_p
            if t:
                wiki_notes_map[t.lower()] = rel_p
        except Exception:
            continue

    # 1. Google Calendar events (today + upcoming)
    try:
        t_events = get_today_events()
        for ev in t_events:
            summary = ev.get("summary", "Event")
            seen_summaries.add(summary.lower())
            ev["source"] = "Google Calendar"
            ev["account"] = ev.get("account") or config.DEFAULT_GOOGLE_ACCOUNT
            ev["reminder_set"] = True
            ev_id = ev.get("id") or ""
            ev["wiki_path"] = wiki_notes_map.get(str(ev_id)) or wiki_notes_map.get(summary.lower()) or ""
            events.append(ev)
    except Exception:
        pass

    try:
        u_events = get_upcoming_events(max_results=15, days=14)
        for ev in u_events:
            summary = ev.get("summary", "Event")
            if summary.lower() not in seen_summaries:
                seen_summaries.add(summary.lower())
                ev["source"] = "Google Calendar"
                ev["account"] = ev.get("account") or config.DEFAULT_GOOGLE_ACCOUNT
                ev["reminder_set"] = True
                ev_id = ev.get("id") or ""
                ev["wiki_path"] = wiki_notes_map.get(str(ev_id)) or wiki_notes_map.get(summary.lower()) or ""
                events.append(ev)
    except Exception:
        pass

    # 2. Captured meeting notes in wiki (only today or future scheduled events)
    for wiki_file in config.WIKI_DIR.glob("*/*.md"):
        if wiki_file.name.startswith("."):
            continue
        try:
            post = frontmatter.load(wiki_file)
            title = str(post.get("title", wiki_file.stem)).strip()
            summary = str(post.get("summary", "")).strip()
            body = post.content
            
            text_check = f"{title} {summary} {body}"
            is_schedulable, _, start_dt, _ = is_schedulable_event(text_check)

            is_meeting_note = bool(post.get("is_meeting")) or bool(post.get("calendar_event_link")) or bool(post.get("calendar_event_start")) or is_schedulable
            status = post.get("calendar_event_status")

            if is_meeting_note and status != "deleted":
                if title.lower() not in seen_summaries:
                    seen_summaries.add(title.lower())
                    cal_link = post.get("calendar_event_link") or format_google_calendar_template_url(summary=title, start_dt=start_dt, description=summary)
                    events.append({
                        "id": post.get("calendar_event_id") or "",
                        "summary": title,
                        "start_time": post.get("calendar_event_start") or start_dt.strftime("%Y-%m-%d %H:%M"),
                        "end_time": post.get("calendar_event_end") or "",
                        "location": post.get("location", ""),
                        "description": summary,
                        "html_link": cal_link,
                        "account": post.get("calendar_account", config.DEFAULT_GOOGLE_ACCOUNT),
                        "wiki_path": str(wiki_file.relative_to(config.ROOT)),
                        "reminder_set": True,
                        "source": "Captured Event",
                    })

        except Exception:
            continue

    return events


def format_event_time_range(st_time: str, end_time: str = "") -> str:
    """Format raw ISO or datetime strings into clean, user-friendly readable date & time with spacing."""
    if not st_time:
        return ""
    try:
        dt_start = parse_datetime_string(st_time)
        date_str = dt_start.strftime("%b %d, %Y")
        time_str = dt_start.strftime("%I:%M %p")

        if end_time:
            try:
                dt_end = parse_datetime_string(end_time)
                if dt_end.date() == dt_start.date():
                    end_time_str = dt_end.strftime("%I:%M %p")
                    return f"📅 <b>Date:</b> {date_str} &nbsp;&nbsp;|&nbsp;&nbsp; ⏰ <b>Time:</b> {time_str} – {end_time_str}"
                else:
                    end_date_str = dt_end.strftime("%b %d, %Y")
                    end_time_str = dt_end.strftime("%I:%M %p")
                    return f"📅 <b>Start:</b> {date_str} at {time_str} &nbsp;&nbsp;→&nbsp;&nbsp; <b>End:</b> {end_date_str} at {end_time_str}"
            except Exception:
                pass

        return f"📅 <b>Date:</b> {date_str} &nbsp;&nbsp;|&nbsp;&nbsp; ⏰ <b>Time:</b> {time_str}"
    except Exception:
        clean_start = str(st_time).replace("T", " ").strip()
        clean_end = str(end_time).replace("T", " ").strip() if end_time else ""
        return f"⏰ <b>Date & Time:</b> {clean_start}" + (f" &nbsp;→&nbsp; {clean_end}" if clean_end else "")


def remove_calendar_event_or_schedule(ev: dict) -> str:
    """Delete event from Google Calendar (if ID present) and/or remove schedule metadata from linked Markdown note."""
    msg_parts = []
    
    # 1. Delete from Google Calendar if event ID is present
    event_id = ev.get("id") or ev.get("calendar_event_id")
    if event_id and not str(event_id).startswith("evt-"):
        try:
            res = delete_event(event_id)
            if res.get("status") == "success":
                msg_parts.append("Removed from Google Calendar")
            else:
                msg_parts.append(f"Calendar notice: {res.get('message')}")
        except Exception as exc:
            msg_parts.append(f"Calendar error: {exc}")
    elif event_id:
        msg_parts.append("Removed local schedule")

    # 2. Update linked wiki note if wiki_path or matching title exists
    wiki_p = ev.get("wiki_path")
    target_notes = []
    if wiki_p:
        np = config.ROOT / wiki_p
        if np.exists():
            target_notes.append(np)
    
    summary_lower = str(ev.get("summary", "")).strip().lower()
    for wf in config.WIKI_DIR.glob("*/*.md"):
        if wf in target_notes:
            continue
        try:
            p = frontmatter.load(wf)
            if (event_id and p.get("calendar_event_id") == event_id) or (summary_lower and str(p.get("title", "")).strip().lower() == summary_lower):
                target_notes.append(wf)
        except Exception:
            continue

    for np in target_notes:
        try:
            post = frontmatter.load(np)
            post.metadata["is_meeting"] = False
            post.metadata["calendar_event_status"] = "deleted"
            for k in ["calendar_event_id", "calendar_event_link", "calendar_event_start", "calendar_event_end"]:
                if k in post.metadata:
                    del post.metadata[k]
            np.write_text(frontmatter.dumps(post), encoding="utf-8")
            msg_parts.append(f"Updated note `{np.name}`")
        except Exception as exc:
            msg_parts.append(f"Note update error: {exc}")

    # 3. Rebuild knowledge graph
    try:
        build_graph()
    except Exception:
        pass

    if not msg_parts:
        msg_parts.append("Event schedule deleted")

    return " | ".join(msg_parts)


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
    """Generate HTML string for 3D Geodesic Sphere interactive knowledge graph visualization using Three.js."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    category_colors = {
        "Projects": "#ef4444",   # Glowing Red
        "Areas": "#10b981",      # Glowing Emerald
        "Resources": "#8b5cf6",  # Glowing Purple
        "Archives": "#64748b",   # Slate Gray
    }

    clean_nodes = []
    for node in nodes:
        cat = node.get("category", "Resources")
        color = category_colors.get(cat, "#3b82f6")
        clean_nodes.append({
            "id": str(node.get("id", "")),
            "label": str(node.get("label", "Untitled")),
            "category": cat,
            "color": color,
            "tags": node.get("tags", []),
            "summary": str(node.get("summary", "")),
            "wiki_path": str(node.get("wiki_path", ""))
        })

    clean_edges = []
    for edge in edges:
        clean_edges.append({
            "source": str(edge.get("source", "")),
            "target": str(edge.get("target", "")),
            "weight": float(edge.get("weight", 1.0)),
            "type": str(edge.get("type", "semantic"))
        })

    json_nodes = json.dumps(clean_nodes)
    json_edges = json.dumps(clean_edges)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #0b0f19;
          color: #f8fafc;
          font-family: 'Inter', system-ui, -apple-system, sans-serif;
          overflow: hidden;
          width: 100vw;
          height: {height_px}px;
        }}
        #container {{
          position: relative;
          width: 100%;
          height: 100%;
          background: radial-gradient(circle at center, #1e293b 0%, #0b0f19 100%);
          border-radius: 12px;
          border: 1px solid rgba(99, 102, 241, 0.3);
          box-shadow: inset 0 0 30px rgba(0,0,0,0.8);
        }}
        #canvas-3d {{
          width: 100%;
          height: 100%;
          display: block;
        }}
        .controls-bar {{
          position: absolute;
          bottom: 14px;
          left: 14px;
          display: flex;
          gap: 8px;
          z-index: 10;
        }}
        .btn-ctrl {{
          background: rgba(30, 41, 59, 0.75);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #cbd5e1;
          padding: 5px 10px;
          border-radius: 6px;
          font-size: 0.75rem;
          cursor: pointer;
          backdrop-filter: blur(8px);
          transition: all 0.2s ease;
        }}
        .btn-ctrl:hover {{
          background: rgba(99, 102, 241, 0.3);
          border-color: #6366f1;
          color: #fff;
        }}
        .node-tooltip {{
          position: absolute;
          top: 14px;
          right: 14px;
          width: 280px;
          background: rgba(15, 23, 42, 0.88);
          border: 1px solid rgba(99, 102, 241, 0.4);
          border-radius: 10px;
          padding: 12px 14px;
          backdrop-filter: blur(12px);
          box-shadow: 0 10px 25px rgba(0,0,0,0.5);
          display: none;
          z-index: 20;
          pointer-events: auto;
          transition: opacity 0.2s ease;
        }}
        .tooltip-title {{
          font-size: 0.92rem;
          font-weight: 600;
          color: #f8fafc;
          margin-bottom: 4px;
        }}
        .tooltip-cat {{
          display: inline-block;
          font-size: 0.68rem;
          font-weight: 700;
          text-transform: uppercase;
          padding: 2px 8px;
          border-radius: 12px;
          margin-bottom: 8px;
        }}
        .tooltip-summary {{
          font-size: 0.78rem;
          color: #cbd5e1;
          line-height: 1.35;
          margin-bottom: 8px;
          max-height: 80px;
          overflow-y: auto;
        }}
        .tooltip-tags {{
          font-size: 0.7rem;
          color: #94a3b8;
        }}
        .legend-bar {{
          position: absolute;
          top: 14px;
          right: 14px;
          display: flex;
          gap: 10px;
          background: rgba(15, 23, 42, 0.6);
          padding: 6px 12px;
          border-radius: 20px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(8px);
          z-index: 10;
        }}
        .legend-item {{
          display: flex;
          align-items: center;
          gap: 5px;
          font-size: 0.72rem;
          color: #cbd5e1;
        }}
        .legend-dot {{
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }}
      </style>

      <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    </head>
    <body>
      <div id="container">
        <div class="legend-bar" id="legendBar">
          <div class="legend-item"><div class="legend-dot" style="background:#ef4444;"></div> Projects</div>
          <div class="legend-item"><div class="legend-dot" style="background:#10b981;"></div> Areas</div>
          <div class="legend-item"><div class="legend-dot" style="background:#8b5cf6;"></div> Resources</div>
          <div class="legend-item"><div class="legend-dot" style="background:#64748b;"></div> Archives</div>
        </div>

        <div class="node-tooltip" id="tooltip">
          <div class="tooltip-title" id="ttTitle">Node Title</div>
          <div class="tooltip-cat" id="ttCat">Category</div>
          <div class="tooltip-summary" id="ttSummary">Summary content...</div>
          <div class="tooltip-tags" id="ttTags">Tags: none</div>
        </div>

        <div class="controls-bar">
          <button class="btn-ctrl" id="btnAutoRotate">Auto-Rotate: ON</button>
          <button class="btn-ctrl" id="btnResetView">Reset View</button>
        </div>

        <canvas id="canvas-3d"></canvas>
      </div>

      <script>
        const nodesData = {json_nodes};
        const edgesData = {json_edges};

        const container = document.getElementById('container');
        const canvas = document.getElementById('canvas-3d');
        const tooltip = document.getElementById('tooltip');
        const legendBar = document.getElementById('legendBar');

        let scene, camera, renderer, controls;
        let geodesicGroup, nodesGroup, edgesGroup, particlesGroup;
        let nodeMeshes = [];
        let edgeLines = [];
        let isAutoRotate = true;
        let hoveredNode = null;

        const SPHERE_RADIUS = 180;

        function init() {{
          // Scene
          scene = new THREE.Scene();

          // Camera
          camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 1, 3000);
          camera.position.set(0, 50, 480);

          // Renderer
          renderer = new THREE.WebGLRenderer({{ canvas: canvas, antialias: true, alpha: true }});
          renderer.setSize(container.clientWidth, container.clientHeight);
          renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

          // OrbitControls
          controls = new THREE.OrbitControls(camera, renderer.domElement);
          controls.enableDamping = true;
          controls.dampingFactor = 0.05;
          controls.rotateSpeed = 0.8;
          controls.zoomSpeed = 1.0;
          controls.maxDistance = 1000;
          controls.minDistance = 100;

          // Lighting
          const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
          scene.add(ambientLight);

          const dirLight1 = new THREE.DirectionalLight(0x38bdf8, 1.2);
          dirLight1.position.set(300, 400, 300);
          scene.add(dirLight1);

          const dirLight2 = new THREE.DirectionalLight(0xa855f7, 0.8);
          dirLight2.position.set(-300, -300, -200);
          scene.add(dirLight2);

          // Parent Groups
          geodesicGroup = new THREE.Group();
          nodesGroup = new THREE.Group();
          edgesGroup = new THREE.Group();
          particlesGroup = new THREE.Group();

          geodesicGroup.add(nodesGroup);
          geodesicGroup.add(edgesGroup);
          scene.add(geodesicGroup);
          scene.add(particlesGroup);

          buildGeodesicStructure();
          buildNodes();
          buildEdges();
          buildBackgroundParticles();

          // Interactivity
          window.addEventListener('resize', onWindowResize);
          canvas.addEventListener('mousemove', onMouseMove);

          document.getElementById('btnAutoRotate').addEventListener('click', () => {{
            isAutoRotate = !isAutoRotate;
            document.getElementById('btnAutoRotate').textContent = 'Auto-Rotate: ' + (isAutoRotate ? 'ON' : 'OFF');
          }});

          document.getElementById('btnResetView').addEventListener('click', () => {{
            camera.position.set(0, 50, 480);
            controls.target.set(0, 0, 0);
            controls.update();
          }});

          animate();
        }}

        function buildGeodesicStructure() {{
          // Icosahedron detail 2 creates a true Geodesic Sphere layout mesh
          const icoGeo = new THREE.IcosahedronGeometry(SPHERE_RADIUS, 2);

          // Wireframe Cage
          const wireframeGeo = new THREE.WireframeGeometry(icoGeo);
          // LineBasicMaterial is part of the core Three.js build loaded above.
          // (LineMaterial requires an additional examples module.)
          const wireframeMat = new THREE.LineBasicMaterial({{
            color: 0x6366f1,
            transparent: true,
            opacity: 0.18
          }});
          const wireframeMesh = new THREE.LineSegments(wireframeGeo, wireframeMat);
          geodesicGroup.add(wireframeMesh);

          // Geodesic Vertices Glowing Lattice Points
          const ptsMat = new THREE.PointsMaterial({{
            color: 0x38bdf8,
            size: 3,
            transparent: true,
            opacity: 0.4
          }});
          const ptsMesh = new THREE.Points(icoGeo, ptsMat);
          geodesicGroup.add(ptsMesh);
        }}

        function buildNodes() {{
          const numNodes = nodesData.length;
          const nodePosMap = new Map();

          nodesData.forEach((node, i) => {{
            // Uniform spherical distribution across Geodesic Sphere surface (Fibonacci sphere algorithm)
            const phi = Math.acos(1 - 2 * (i + 0.5) / Math.max(1, numNodes));
            const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);

            const r = SPHERE_RADIUS;
            const x = r * Math.sin(phi) * Math.cos(theta);
            const y = r * Math.sin(phi) * Math.sin(theta);
            const z = r * Math.cos(phi);

            const pos = new THREE.Vector3(x, y, z);
            nodePosMap.set(node.id, pos);

            // Node Sphere Mesh
            // Keep all graph nodes equally small; category color conveys type.
            const radiusSize = 4;
            const sphereGeo = new THREE.SphereGeometry(radiusSize, 24, 24);
            const sphereMat = new THREE.MeshPhongMaterial({{
              color: new THREE.Color(node.color),
              emissive: new THREE.Color(node.color).multiplyScalar(0.35),
              shininess: 90,
              transparent: true,
              opacity: 0.95
            }});

            const mesh = new THREE.Mesh(sphereGeo, sphereMat);
            mesh.position.copy(pos);
            mesh.userData = {{ nodeData: node, originalScale: 1.0, color: node.color, pos: pos }};

            // Glow Ring Sprite
            const canvasGlow = document.createElement('canvas');
            canvasGlow.width = 64; canvasGlow.height = 64;
            const ctx = canvasGlow.getContext('2d');
            const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, node.color);
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.fillRect(0,0,64,64);

            const texture = new THREE.CanvasTexture(canvasGlow);
            const spriteMat = new THREE.SpriteMaterial({{ map: texture, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending }});
            const sprite = new THREE.Sprite(spriteMat);
            sprite.scale.set(radiusSize * 2.5, radiusSize * 2.5, 1);
            mesh.add(sprite);

            nodesGroup.add(mesh);
            nodeMeshes.push(mesh);
          }});

          window.nodePosMap = nodePosMap;
        }}

        function buildEdges() {{
          const nodePosMap = window.nodePosMap;
          if (!nodePosMap) return;

          edgesData.forEach(edge => {{
            const p1 = nodePosMap.get(edge.source);
            const p2 = nodePosMap.get(edge.target);

            if (p1 && p2) {{
              // Elevate curve outward above sphere surface for 3D geodesic arc feel
              const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
              const midLength = mid.length();
              if (midLength > 0) {{
                mid.normalize().multiplyScalar(SPHERE_RADIUS * (1.12 + edge.weight * 0.08));
              }}

              const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
              const points = curve.getPoints(30);
              const curveGeo = new THREE.BufferGeometry().setFromPoints(points);

              const lineMat = new THREE.LineBasicMaterial({{
                color: 0x818cf8,
                transparent: true,
                opacity: Math.max(0.25, Math.min(0.7, edge.weight * 0.6))
              }});

              const line = new THREE.Line(curveGeo, lineMat);
              line.userData = {{ source: edge.source, target: edge.target, originalOpacity: lineMat.opacity }};
              edgesGroup.add(line);
              edgeLines.push(line);
            }}
          }});
        }}

        function buildBackgroundParticles() {{
          const count = 350;
          const pGeo = new THREE.BufferGeometry();
          const pPos = new Float32Array(count * 3);

          for (let i = 0; i < count * 3; i += 3) {{
            pPos[i] = (Math.random() - 0.5) * 1200;
            pPos[i+1] = (Math.random() - 0.5) * 1200;
            pPos[i+2] = (Math.random() - 0.5) * 1200;
          }}

          pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
          const pMat = new THREE.PointsMaterial({{
            color: 0x475569,
            size: 2,
            transparent: true,
            opacity: 0.5
          }});

          const pMesh = new THREE.Points(pGeo, pMat);
          particlesGroup.add(pMesh);
        }}

        function onMouseMove(event) {{
          const rect = canvas.getBoundingClientRect();
          const mouse = new THREE.Vector2(
            ((event.clientX - rect.left) / container.clientWidth) * 2 - 1,
            -((event.clientY - rect.top) / container.clientHeight) * 2 + 1
          );

          const raycaster = new THREE.Raycaster();
          raycaster.setFromCamera(mouse, camera);

          const intersects = raycaster.intersectObjects(nodeMeshes);

          if (intersects.length > 0) {{
            const hitMesh = intersects[0].object;
            if (hoveredNode !== hitMesh) {{
              resetHighlight();
              hoveredNode = hitMesh;
              highlightNode(hitMesh);
            }}
          }} else {{
            if (hoveredNode) {{
              resetHighlight();
              hoveredNode = null;
            }}
          }}
        }}

        function highlightNode(mesh) {{
          mesh.scale.set(1.5, 1.5, 1.5);
          mesh.material.emissive.setHex(0x38bdf8);

          const nData = mesh.userData.nodeData;

          // Tooltip Populating
          document.getElementById('ttTitle').textContent = nData.label;
          const catElem = document.getElementById('ttCat');
          catElem.textContent = nData.category;
          catElem.style.background = nData.color + '33';
          catElem.style.color = nData.color;
          catElem.style.border = '1px solid ' + nData.color;

          document.getElementById('ttSummary').textContent = nData.summary || 'No summary available.';
          document.getElementById('ttTags').textContent = 'Tags: ' + (nData.tags && nData.tags.length ? nData.tags.join(', ') : 'none');

          tooltip.style.display = 'block';
          legendBar.style.display = 'none';

          // Edge Highlighting
          edgeLines.forEach(line => {{
            if (line.userData.source === nData.id || line.userData.target === nData.id) {{
              line.material.opacity = 0.9;
              line.material.color.setHex(0x38bdf8);
            }} else {{
              line.material.opacity = 0.08;
            }}
          }});
        }}

        function resetHighlight() {{
          nodeMeshes.forEach(mesh => {{
            mesh.scale.set(1, 1, 1);
            mesh.material.emissive.copy(new THREE.Color(mesh.userData.color).multiplyScalar(0.35));
          }});

          edgeLines.forEach(line => {{
            line.material.opacity = line.userData.originalOpacity;
            line.material.color.setHex(0x818cf8);
          }});

          tooltip.style.display = 'none';
          legendBar.style.display = 'flex';
        }}

        function onWindowResize() {{
          camera.aspect = container.clientWidth / container.clientHeight;
          camera.updateProjectionMatrix();
          renderer.setSize(container.clientWidth, container.clientHeight);
        }}

        function animate() {{
          requestAnimationFrame(animate);

          if (isAutoRotate && !hoveredNode) {{
            geodesicGroup.rotation.y += 0.003;
            geodesicGroup.rotation.x += 0.001;
            particlesGroup.rotation.y += 0.0005;
          }}

          controls.update();
          renderer.render(scene, camera);
        }}

        window.onload = init;
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
                        
                        is_sched, title_sch, dt_sch, _ = is_schedulable_event(note_input)
                        if is_sched:
                            st.toast(f"📅 Meeting sent to Google Calendar for {dt_sch.strftime('%b %d at %I:%M %p')}.", icon="🔔")
                        else:
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
                        
                        is_sched, title_sch, dt_sch, _ = is_schedulable_event(edited_transcript)
                        st.session_state["voice_transcript"] = ""
                        st.session_state["recorded_audio_bytes"] = None

                        if is_sched:
                            st.toast(f"📅 Spoken meeting scheduled & reminder set on Google Calendar for {dt_sch.strftime('%b %d at %I:%M %p')}!", icon="🔔")
                        else:
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
        st.header("📅 Google Calendar Sync")
        if google_service_manager.is_authenticated():
            st.success("✅ Live Google Calendar OAuth Connected")
        elif google_service_manager.has_client_secrets():
            st.info("🔑 `client_secret.json` detected!")
            if st.button("🔐 Authorize Google Account", use_container_width=True):
                with st.spinner("Opening browser to authorize Google Calendar account..."):
                    try:
                        creds = google_service_manager.get_credentials()
                        if creds and creds.valid:
                            st.success("🎉 Google Calendar authenticated!")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Auth error: {exc}")
        else:
            st.caption("Place `client_secret.json` in `credentials/` folder to enable direct OAuth sync.")

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

    if "show_events" not in st.session_state:
        st.session_state["show_events"] = False

    if q_cols[0].button("🚀 Projects", use_container_width=True):
        query_input = "What projects am I currently working on?"
        st.session_state["show_events"] = False
    if q_cols[1].button("🤖 RAG Notes", use_container_width=True):
        query_input = "What did I capture about RAG architecture?"
        st.session_state["show_events"] = False
    if q_cols[2].button("📅 Events", use_container_width=True):
        st.session_state["show_events"] = not st.session_state.get("show_events", False)

    if st.session_state.get("show_events"):
        with st.spinner("Fetching Google Calendar events & linked meeting reminders..."):
            all_events = get_all_calendar_events_and_meetings()
            st.markdown("### 📅 Google Calendar Events & Linked Meetings")
            if all_events:
                st.success(f"Found {len(all_events)} event(s) & meeting reminder(s) for {config.DEFAULT_GOOGLE_ACCOUNT}:")
                for idx, ev in enumerate(all_events):
                    summary = ev.get("summary", "Event")
                    st_time = ev.get("start_time", "")
                    end_time = ev.get("end_time", "")
                    loc = ev.get("location", "")
                    desc = ev.get("description", "")
                    acc = ev.get("account", config.DEFAULT_GOOGLE_ACCOUNT)
                    raw_link = ev.get("html_link", "")
                    ev_id = ev.get("id") or ev.get("calendar_event_id") or f"ev_{idx}"
                    wiki_p = ev.get("wiki_path", "")

                    if raw_link and "action=TEMPLATE" in raw_link:
                        link = raw_link
                    else:
                        st_dt = parse_datetime_string(st_time)
                        link = format_google_calendar_template_url(summary=summary, start_dt=st_dt, description=desc, location=loc)

                    card_col, btn_col = st.columns([4, 1])
                    with card_col:
                        desc_html = f"<br/>📝 <b>Description:</b> {desc}" if desc else ""
                        formatted_time = format_event_time_range(st_time, end_time)
                        time_html = f"<br/>{formatted_time}" if formatted_time else ""
                        loc_html = f"<br/>📍 <b>Location:</b> {loc}" if loc else ""
                        wiki_html = f"<br/>📄 <b>Linked SecondSelf Note:</b> <code>{wiki_p}</code>" if wiki_p else ""

                        st.markdown(
                            f'<div class="card" style="border-left: 4px solid #3b82f6; margin-bottom: 12px; padding: 14px;">'
                            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
                            f'<div>'
                            f'<h4 style="margin: 0 0 6px 0; color: #ffffff; font-size: 1.15rem; font-weight: 700;">📅 {summary}</h4>'
                            f'<span style="background-color: #dbeafe; color: #1e40af; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;">📧 Account: {acc}</span> '
                            f'<span style="background-color: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;">🔔 Reminder Active (Automatic Sync)</span>'
                            f'{desc_html}'
                            f'{time_html}'
                            f'{loc_html}'
                            f'{wiki_html}'
                            f'</div>'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    with btn_col:
                        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                        if st.button("Delete", key=f"btn_del_ev_{idx}_{ev_id}", use_container_width=True):
                            with st.spinner("Deleting event..."):
                                res_msg = remove_calendar_event_or_schedule(ev)
                            st.toast(f"Deleted event '{summary}'", icon="✅")
                            st.rerun()

            else:
                st.info("No calendar events or meetings found.")


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
        st.markdown(response.answer)

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

                    # Display linked Google Calendar Event & Reminder if meeting
                    try:
                        p = config.ROOT / src.wiki_path
                        if p.exists():
                            fm = frontmatter.load(p)
                            if (fm.get("is_meeting") or fm.get("calendar_event_link")) and fm.get("calendar_event_status") != "deleted":
                                cal_link = fm.get("calendar_event_link")
                                acc = fm.get("calendar_account", config.DEFAULT_GOOGLE_ACCOUNT)
                                src_col1, src_col2 = st.columns([3, 1])
                                with src_col1:
                                    st.markdown(
                                        f'<div style="background-color: #eff6ff; border: 1px solid #bfdbfe; padding: 10px 14px; border-radius: 8px; margin-top: 10px;">'
                                        f'<div style="display: flex; justify-content: space-between; align-items: center;">'
                                        f'<div>'
                                        f'<b>📅 Linked Google Calendar Event & Reminder</b><br/>'
                                        f'<span style="color: #1e40af; font-size: 0.85rem;">📧 Account: <b>{acc}</b></span> | '
                                        f'<span style="color: #166534; font-size: 0.85rem;">🔔 Status: <b>Reminder Active (30m & 10m popup, 1h email)</b></span>'
                                        f'</div>'
                                        f'</div>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                with src_col2:
                                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                                    if st.button("Delete", key=f"del_src_sch_{src.id}", use_container_width=True):
                                        with st.spinner("Deleting schedule..."):
                                            ev_dict = {
                                                "id": fm.get("calendar_event_id") or "",
                                                "summary": src.title,
                                                "wiki_path": src.wiki_path,
                                            }
                                            res_msg = remove_calendar_event_or_schedule(ev_dict)
                                        st.toast(f"Deleted schedule for '{src.title}'", icon="✅")
                                        st.rerun()

                    except Exception:
                        pass


    st.divider()

    # Section 2: Landscape Knowledge Graph below Search
    st.subheader("Knowledge Graph")

    if not nodes:
        st.info("No notes captured yet. Run `python capture.py` and `python classify.py --all` to get started!")
    else:
        graph_html = render_vis_network(graph_data, height_px=540)
        components.html(graph_html, height=560)


if __name__ == "__main__":
    main()


