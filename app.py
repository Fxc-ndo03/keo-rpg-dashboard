# -*- coding: utf-8 -*-
"""
KEO RPG — Dashboard Premium del Servidor (v2).
================================================
Estetica: Modo oscuro profesional (deep warm black) + paleta Beige/Taupe/Crema
inspirada en la linea de marca "Margarita".

Arquitectura (sin Playit, sin puertos raros):
  · Agente local (agent_local.py) → POST /api/push al broker en Render.
  · Broker Render (server.py Flask) → guarda estado actual + historial 1000 pts.
  · Streamlit Community Cloud (este app.py) → GET /api/state + /api/history.

Caracteristicas de esta version:
  · Paleta CUSTOM (Beige / Taupe / Crema / Bronce-Soft) sobre fondo oscuro warm-black.
  · 5 pestañas funcionales: RESUMEN | RENDIMIENTO | JUGADORES | HISTORIAL | INFO.
  · Nuevas metricas: MSPT estimado, Heap % utilizado, Stability Score, Health Index.
  · Graficos avanzados: area combinada TPS/RAM, sparklines, gauge circular TPS/CPU,
    distribucion de carga por tiempo, timeline de conectividad.
  · Botones funcionales: Copiar IP, Copiar Link Dashboard, Forzar Refresh.
  · Total responsive (mobile friendly).
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================
# PALETA DE COLORES PREMIUM (Beige / Taupe / Crema · Dark Mode)
# Inspirada en las referencias "Marca personal Margarita".
# ============================================================
class C:
    """Nombres semanticos para mantener consistencia en todo el dashboard."""
    BG_DEEP       = "#16130F"   # Fondo principal: warm black (cafe muy oscuro)
    BG_SURFACE    = "#1E1A14"   # Tarjetas: cafe-negro 2 tono mas claro
    BG_SURFACE_2  = "#27221A"   # Tarjetas internas / tablas
    BG_ELEVATED   = "#302A21"   # Btn / campos hover
    BDR           = "#443A2C"   # Bordes tarjetas (taupe oscuro)
    BDR_SOFT      = "#332B21"   # Bordes secundarios
    TEXT          = "#EFE6D5"   # Crema claro (texto principal)
    TEXT_MUTED    = "#B7A98E"   # Taupe medio (texto secundario)
    TEXT_SUBTLE   = "#8B7E66"   # Taupe oscuro (texto terciario)
    ACCENT        = "#C99E6A"   # Bronce suave / Beige dorado (CTA principal)
    ACCENT_2      = "#B8956A"   # Bronce mas oscuro (secundario)
    ACCENT_SOFT   = "#E4CFAC"   # Beige claro luminoso (iconos)
    OK            = "#9BB58C"   # Verde salvia suave (no verde brillante)
    WARN          = "#D7B26C"   # Beige-amarillo (warning)
    CRIT          = "#C27D71"   # Terracota-rosado (critico)
    PLOT_1        = "#C99E6A"   # TPS
    PLOT_2        = "#B8956A"   # RAM
    PLOT_3        = "#9BB58C"   # CPU
    PLOT_4        = "#D9C28F"   # Players
    PLOT_5        = "#7D8FA7"   # MSPT (acero suave)

PALETTE_PLOT = [C.PLOT_1, C.PLOT_2, C.PLOT_3, C.PLOT_4, C.PLOT_5]

# ============================================================
# CONFIG STREAMLIT GLOBAL (base)
# ============================================================
st.set_page_config(
    page_title="KEO RPG · Monitor del Servidor",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"Get help": None, "Report a bug": None, "About": None},
)

MAX_HISTORY_POINTS = 300
STALE_THRESHOLD_SECONDS = 120

SERVER_IPS = [
    ("visual-stay.gl.joinmc.link", "Host Principal"),
    ("stank-understood.tun.ply.gg", "Host Alternativo"),
]

# ============================================================
# 1. CSS CUSTOM INYECTADO (estetica Beige/Taupe · Dark Mode)
# ============================================================
def inject_css() -> None:
    # El background de Streamlit y el sidebar ya tienen CSS base; lo pisamos.
    # Usamos raw CSS para colores exactos, tipografia Inter, tarjetas, botones,
    # inputs, tabs, st.metric, etc.
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"]  {{
            font-family: 'Inter', system-ui, sans-serif !important;
            color: {C.TEXT};
        }}

        /* ---- FONDO ---- */
        .stApp, [data-testid="stAppViewContainer"]  {{
            background: radial-gradient(1200px 600px at 10% -10%, #221c15 0%, transparent 60%),
                        radial-gradient(900px 500px at 110% 10%, #1d1811 0%, transparent 55%),
                        linear-gradient(180deg, {C.BG_DEEP} 0%, #120F0B 100%);
        }}
        header[data-testid="stHeader"] {{ background: transparent; }}

        /* ---- TIPOGRAFIA ---- */
        h1, h2, h3, h4, h5, h6 {{ color: {C.TEXT}; font-weight: 700; letter-spacing: -0.01em; }}
        p, span, li, label {{ color: {C.TEXT}; }}
        .stMarkdown small {{ color: {C.TEXT_MUTED}; }}

        /* ---- TARJETAS ---- */
        [data-testid="stVerticalBlock"] [data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stMetric"],
        div[data-testid="stHorizontalBlock"] > div > div > div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: linear-gradient(180deg, {C.BG_SURFACE} 0%, {C.BG_SURFACE_2} 100%) !important;
            border: 1px solid {C.BDR} !important;
            border-radius: 14px !important;
            box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.03);
            padding: 14px 16px !important;
        }}

        div[data-testid="stMetric"] {{
            padding: 12px 14px !important;
        }}
        div[data-testid="stMetric"] label[data-testid="stMetricLabel"] p {{
            color: {C.TEXT_MUTED} !important;
            font-size: 12px !important;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 600;
        }}
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            color: {C.TEXT} !important;
            font-weight: 800 !important;
            font-size: 30px !important;
            letter-spacing: -0.02em;
            margin-top: 4px;
        }}
        div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {{
            color: {C.ACCENT_SOFT} !important;
            font-weight: 500;
            font-size: 13px;
        }}

        /* ---- BOTONES (Streamlit default) ---- */
        .stButton > button, .stDownloadButton > button,
        .stLinkButton > a, .stFormSubmitButton > button {{
            background: linear-gradient(180deg, {C.ACCENT} 0%, {C.ACCENT_2} 100%) !important;
            color: #1A1510 !important;
            font-weight: 700 !important;
            border: 1px solid #8E6A3F !important;
            border-radius: 10px !important;
            padding: 8px 16px !important;
            box-shadow: 0 6px 16px rgba(201, 158, 106, 0.18), inset 0 1px 0 rgba(255,255,255,0.18);
            letter-spacing: 0.02em;
            transition: all 0.15s ease;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(201, 158, 106, 0.28), inset 0 1px 0 rgba(255,255,255,0.25);
            background: linear-gradient(180deg, #D2A976 0%, {C.ACCENT} 100%) !important;
        }}

        /* ---- TABS ---- */
        div[data-testid="stTabs"] {{
            background: {C.BG_SURFACE};
            border: 1px solid {C.BDR};
            border-radius: 16px;
            padding: 10px 12px 14px 12px;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
            gap: 8px;
            margin-bottom: 14px;
            padding-bottom: 8px;
            border-bottom: 1px solid {C.BDR_SOFT};
        }}
        div[data-testid="stTabs"] [data-baseweb="tab"] {{
            background: transparent;
            color: {C.TEXT_MUTED};
            font-weight: 600;
            font-size: 13.5px;
            letter-spacing: 0.03em;
            padding: 8px 14px;
            border-radius: 10px;
            border: 1px solid transparent;
            transition: all 0.15s ease;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover {{
            color: {C.TEXT};
            background: {C.BG_ELEVATED};
            border-color: {C.BDR};
        }}
        div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
            background: linear-gradient(180deg, rgba(201,158,106,0.16), rgba(201,158,106,0.06));
            color: {C.ACCENT_SOFT};
            border-color: #8E6A3F55;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ display: none; }}
        div[data-testid="stTabs"] [data-baseweb="tab-border"]  {{ display: none; }}

        /* ---- EXPANDERS ---- */
        [data-testid="stExpander"] {{
            background: {C.BG_SURFACE};
            border: 1px solid {C.BDR};
            border-radius: 14px;
        }}
        [data-testid="stExpander"] details summary p {{ color: {C.TEXT}; font-weight: 700; }}

        /* ---- SELECTBOX / INPUTS ---- */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div {{
            background: {C.BG_SURFACE_2} !important;
            border-color: {C.BDR} !important;
            color: {C.TEXT} !important;
            border-radius: 10px !important;
        }}
        div[data-baseweb="select"] span,
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea {{
            color: {C.TEXT} !important;
        }}
        ul[role="listbox"] {{ background: {C.BG_SURFACE_2} !important; border: 1px solid {C.BDR} !important; }}
        ul[role="listbox"] li[aria-selected="true"] {{ background: #8E6A3F55 !important; color: {C.ACCENT_SOFT} !important; }}

        /* ---- CODE BLOCKS / MONO ---- */
        code, pre, .mono {{ font-family: 'JetBrains Mono', monospace !important; }}
        code {{
            background: #0F0C09 !important;
            color: {C.ACCENT_SOFT} !important;
            border: 1px solid {C.BDR_SOFT} !important;
            border-radius: 6px;
            padding: 2px 6px !important;
            font-size: 0.9em !important;
        }}

        /* ---- CHECKBOX / RADIO ---- */
        label[data-baseweb="checkbox"] div,
        label[data-baseweb="radio"] div:nth-child(1) {{
            background: {C.BG_SURFACE_2} !important;
            border-color: {C.BDR} !important;
        }}

        /* ---- DATAFRAMES / TABLAS ---- */
        [data-testid="stDataFrame"] {{
            background: {C.BG_SURFACE_2};
            border: 1px solid {C.BDR};
            border-radius: 12px;
            padding: 4px;
        }}

        /* ---- DIVISOR ---- */
        hr {{ border: none; border-top: 1px solid {C.BDR_SOFT}; margin: 8px 0 14px 0; }}

        /* ---- PILL / BADGE custom ---- */
        .pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 10px; border-radius: 999px;
            font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
            border: 1px solid {C.BDR};
            background: {C.BG_SURFACE_2}; color: {C.TEXT_MUTED};
        }}
        .pill-ok    {{ background: #2B3123; color: {C.OK};   border-color: #3F4A32; }}
        .pill-warn  {{ background: #312A1A; color: {C.WARN}; border-color: #52431F; }}
        .pill-crit  {{ background: #321E1B; color: {C.CRIT}; border-color: #552B25; }}
        .pill-accent{{ background: #3A2D1A; color: {C.ACCENT_SOFT}; border-color: #8E6A3F55; }}

        /* ---- HERO TOP BAR ---- */
        .hero-bar {{
            background: linear-gradient(90deg, #231C14 0%, #1D1811 60%, #2A2217 100%);
            border: 1px solid {C.BDR};
            border-radius: 18px;
            padding: 18px 22px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 14px;
            box-shadow: 0 14px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04);
            margin-bottom: 16px;
        }}
        .hero-title {{
            font-size: 26px; font-weight: 800; letter-spacing: -0.02em; color: {C.TEXT};
            display: flex; align-items: center; gap: 10px;
        }}
        .hero-sub {{ color: {C.TEXT_MUTED}; font-size: 13px; margin-top: 4px; }}
        .hero-actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}

        /* ---- STATUS LED ---- */
        .led {{ width: 10px; height: 10px; border-radius: 50%; display:inline-block; }}
        .led-on  {{ background: {C.OK};  box-shadow: 0 0 0 4px #9BB58C33, 0 0 16px #9BB58C77; }}
        .led-off {{ background: {C.CRIT}; box-shadow: 0 0 0 4px #C27D7133; }}
        .led-warn{{ background: {C.WARN}; box-shadow: 0 0 0 4px #D7B626633; }}

        /* ---- KPI Cards pequeñas con icono ---- */
        .kpi {{
            display: flex; align-items: flex-start; gap: 12px;
            background: linear-gradient(180deg, {C.BG_SURFACE} 0%, {C.BG_SURFACE_2} 100%);
            border: 1px solid {C.BDR}; border-radius: 14px; padding: 14px 16px;
            box-shadow: 0 8px 22px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03);
        }}
        .kpi-icon {{
            width: 40px; height: 40px; flex:0 0 40px; border-radius: 10px;
            display:flex; align-items:center; justify-content:center;
            background: #3A2D1A; color: {C.ACCENT_SOFT};
            border: 1px solid #8E6A3F55; font-size: 18px; font-weight: 800;
        }}
        .kpi-label {{ color: {C.TEXT_MUTED}; font-size: 12px; font-weight: 600;
                      letter-spacing: 0.08em; text-transform: uppercase; }}
        .kpi-value {{ color: {C.TEXT}; font-size: 24px; font-weight: 800;
                      letter-spacing: -0.02em; line-height: 1.15; margin-top: 4px; }}
        .kpi-sub   {{ color: {C.TEXT_SUBTLE}; font-size: 12px; margin-top: 4px; }}

        /* ---- IP Pill ---- */
        .ip-pill {{
            display:inline-flex; align-items:center; gap:8px;
            background: #0F0C09; color: {C.ACCENT_SOFT};
            border: 1px solid {C.BDR_SOFT}; border-radius: 999px;
            padding: 5px 10px; font-family: 'JetBrains Mono', monospace; font-size: 12.5px;
            font-weight: 500;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()

# ============================================================
# 2. BROKER / STATE LOAD (Render + fallback archivo local)
# ============================================================
_GLOBAL_STATE: Dict[str, Any] = {
    "last_push_ts": 0.0,
    "last_payload": None,
    "hist_t": [],
    "hist_ram_gb": [],
    "hist_cpu_pct": [],
    "hist_tps": [],
    "hist_players": [],
    "api_push_total": 0,
}

_AGENT_CFG: Dict[str, Any] = {}
try:
    _CFG_PATH = Path(__file__).resolve().parent / "agent_config.py"
    if _CFG_PATH.exists():
        _raw = _CFG_PATH.read_text(encoding="utf-8", errors="ignore")
        for line in _raw.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#") or "=" not in line_s:
                continue
            k, v = line_s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            _AGENT_CFG[k] = v
except Exception:
    _AGENT_CFG = {}


def _push_history_early(p: Dict[str, Any]) -> None:
    ts_float = float(_GLOBAL_STATE.get("last_push_ts") or 0.0)
    if not ts_float:
        return
    lbl = time.strftime("%H:%M:%S", time.localtime(ts_float))
    _GLOBAL_STATE["hist_t"].append(lbl)
    try: _GLOBAL_STATE["hist_ram_gb"].append(float(p.get("ram_gb") or 0.0))
    except Exception: _GLOBAL_STATE["hist_ram_gb"].append(0.0)
    try: _GLOBAL_STATE["hist_cpu_pct"].append(float(p.get("cpu_pct") or p.get("cpu") or 0.0))
    except Exception: _GLOBAL_STATE["hist_cpu_pct"].append(0.0)
    try: _GLOBAL_STATE["hist_tps"].append(float(p.get("tps") or 0.0))
    except Exception: _GLOBAL_STATE["hist_tps"].append(0.0)
    try: _GLOBAL_STATE["hist_players"].append(int(p.get("players") or 0))
    except Exception: _GLOBAL_STATE["hist_players"].append(0)
    for k in ("hist_t", "hist_ram_gb", "hist_cpu_pct", "hist_tps", "hist_players"):
        while len(_GLOBAL_STATE[k]) > MAX_HISTORY_POINTS:
            _GLOBAL_STATE[k].pop(0)


def _get_render_broker_url() -> str:
    url = str(_AGENT_CFG.get("RENDER_API_URL", "") or "").strip()
    if not url:
        try:
            if hasattr(st, "secrets"):
                url = str(st.secrets.get("RENDER_API_URL", "") or "").strip()
        except Exception:
            url = ""
    if not url:
        url = str(os.environ.get("RENDER_API_URL", "") or "").strip()
    placeholders = ("CAMBIAR", "TU-", "PON-AQUI", "EJEMPLO", "TUAPP")
    for p in placeholders:
        if p in url.upper():
            return ""
    return url.rstrip("/ ")


def _load_state_from_render_broker() -> None:
    base = _get_render_broker_url()
    if not base:
        return
    now = time.time()
    try:
        r1 = requests.get(base + "/api/state", timeout=5)
        if r1.status_code != 200:
            return
        data = r1.json() or {}
        st_obj = data.get("state")
        if st_obj and (not data.get("stale")):
            ts_render = float(
                st_obj.get("timestamp")
                or st_obj.get("_received_at")
                or data.get("ts")
                or 0.0
            )
            if ts_render > float(_GLOBAL_STATE.get("last_push_ts") or 0.0):
                _GLOBAL_STATE["last_push_ts"] = ts_render
                _GLOBAL_STATE["last_payload"] = dict(st_obj)
                _push_history_early(dict(st_obj))
    except Exception:
        return

    try:
        r2 = requests.get(base + "/api/history?limit=180", timeout=5)
        if r2.status_code == 200:
            rows = (r2.json() or {}).get("rows") or []
            if rows:
                parsed: List[Dict[str, Any]] = [r for r in rows if isinstance(r, dict)]
                if parsed:
                    _GLOBAL_STATE["hist_t"] = [
                        str(
                            d.get("t")
                            or datetime.fromtimestamp(
                                int(d.get("ts") or int(d.get("_received_at") or 0))
                            ).strftime("%H:%M:%S")
                        )
                        for d in parsed
                    ]
                    _GLOBAL_STATE["hist_ram_gb"]   = [float(d.get("ram_gb") or 0.0) for d in parsed]
                    _GLOBAL_STATE["hist_cpu_pct"]  = [float(d.get("cpu_pct") or d.get("cpu") or 0.0) for d in parsed]
                    _GLOBAL_STATE["hist_tps"]      = [float(d.get("tps") or 0.0) for d in parsed]
                    _GLOBAL_STATE["hist_players"]  = [int(d.get("players") or 0) for d in parsed]
                    for k in ("hist_t", "hist_ram_gb", "hist_cpu_pct", "hist_tps", "hist_players"):
                        while len(_GLOBAL_STATE[k]) > MAX_HISTORY_POINTS:
                            _GLOBAL_STATE[k].pop(0)
    except Exception:
        pass


def _load_state_from_disk() -> None:
    try:
        web_dir = Path(__file__).resolve().parent
        state_path = web_dir / "_dashboard_state.json"
        if not state_path.exists():
            return
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        last_ts = float(
            state_data.get("ts_float")
            or state_data.get("last_push_ts")
            or state_data.get("ts")
            or 0.0
        )
        now = time.time()
        if last_ts <= 0 or (now - last_ts) > STALE_THRESHOLD_SECONDS:
            return
        payload = state_data.get("last_payload") or {}
        if last_ts > float(_GLOBAL_STATE.get("last_push_ts") or 0.0):
            _GLOBAL_STATE["last_push_ts"] = last_ts
            _GLOBAL_STATE["last_payload"] = payload
            _push_history_early(payload)
    except Exception:
        return


_load_state_from_render_broker()
_load_state_from_disk()

# ============================================================
# 3. HANDLE de __api_push (modo legacy cloud) — no se usa pero se deja
# ============================================================
def _extract_api_json(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("<!--API_JSON:")
    if start == -1:
        return None
    end = text.find(":END_API_JSON-->")
    if end == -1:
        return None
    try:
        return json.loads(text[start + len("<!--API_JSON:"):end])
    except Exception:
        return None


def _handle_api_endpoint_early() -> None:
    try:
        qp = st.query_params
    except Exception:
        return
    try:
        is_push = False
        if hasattr(qp, "get_all"):
            is_push = bool(qp.get_all("__api_push") or qp.get_all("token"))
        else:
            d = dict(qp)
            is_push = ("__api_push" in d) or ("token" in d)
        if not is_push:
            return
    except Exception:
        return

    token_expected = ""
    try:
        token_expected = str(st.secrets.get("AGENT_SECRET_TOKEN", "")).strip()
    except Exception:
        pass
    if not token_expected:
        token_expected = str(_AGENT_CFG.get("AGENT_SECRET_TOKEN", "") or "").strip()
    if not token_expected:
        token_expected = "keo2026-minecraft-servidor-secreto-123"

    def _g(k: str, default: str = "") -> str:
        try:
            if hasattr(qp, "get"):
                return str(qp.get(k) or default)
            return str(dict(qp).get(k) or default)
        except Exception:
            return default

    token_in = _g("token")
    if not token_in or token_in != token_expected:
        html_out = "<!--API_JSON:" + json.dumps({"ok": False, "msg": "token invalido"}, ensure_ascii=False) + ":END_API_JSON-->"
        st.write(html_out + "<html><body>OK</body></html>", unsafe_allow_html=True)
        st.stop()
        return

    t_sent = time.time()
    payload_in = {
        "ram_gb": _g("ram_gb", "0"),
        "cpu_pct": _g("cpu", "0"),
        "tps": _g("tps", "0"),
        "players": _g("players", "0"),
        "mc_up": _g("mc_up", ""),
        "alerts": _g("alerts", "0"),
        "last_msg": _g("last_msg", ""),
        "player_list": _g("player_list", ""),
    }
    try:
        norm = {
            "ram_gb": round(float(payload_in["ram_gb"] or 0), 2),
            "cpu_pct": round(float(payload_in["cpu_pct"] or 0), 1),
            "tps": round(max(0.0, min(20.0, float(payload_in["tps"] or 0))), 2),
            "players": int(payload_in["players"] or 0),
            "mc_up": payload_in["mc_up"],
            "alerts": int(payload_in["alerts"] or 0),
            "last_msg": payload_in["last_msg"],
            "player_list": payload_in["player_list"],
            "timestamp": int(t_sent),
        }
        if t_sent > float(_GLOBAL_STATE.get("last_push_ts") or 0.0):
            _GLOBAL_STATE["last_push_ts"] = t_sent
            _GLOBAL_STATE["last_payload"] = norm
            _push_history_early(norm)
        _GLOBAL_STATE["api_push_total"] = int(_GLOBAL_STATE.get("api_push_total") or 0) + 1
        resp = json.dumps({"ok": True, "hist": len(_GLOBAL_STATE["hist_t"]), "msg": "ok"}, ensure_ascii=False)
    except Exception as e:
        resp = json.dumps({"ok": False, "msg": f"parse-error:{type(e).__name__}"}, ensure_ascii=False)
    st.write(
        "<!--API_JSON:" + resp + ":END_API_JSON--><html><body>OK</body></html>",
        unsafe_allow_html=True,
    )
    st.stop()


_handle_api_endpoint_early()

# ============================================================
# 4. HELPERS GENERALES
# ============================================================
def now() -> float:
    return time.time()


def human_uptime(seconds: float) -> str:
    try:
        seconds = max(0, int(float(seconds or 0)))
    except Exception:
        return "N/A"
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h {m}m"


def pill(cls: str, txt: str) -> str:
    return f"<span class='pill pill-{cls}'>{txt}</span>"


# ============================================================
# 5. GRAFICOS (premium, plotly custom)
# ============================================================
def _plotly_theme() -> Dict[str, Any]:
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  "rgba(0,0,0,0)",
        "font": {"family": "Inter", "color": C.TEXT_MUTED, "size": 11},
        "xaxis": {
            "gridcolor": "#332B21", "linecolor": "#332B21",
            "zerolinecolor": "#332B21", "showticklabels": True,
            "ticks": "outside", "tickcolor": "#332B21",
        },
        "yaxis": {
            "gridcolor": "#332B21", "linecolor": "#332B21",
            "zerolinecolor": "#332B21", "showticklabels": True,
            "ticks": "outside", "tickcolor": "#332B21",
        },
        "colorway": PALETTE_PLOT,
        "legend": {
            "bgcolor": "rgba(30, 26, 20, 0.85)",
            "bordercolor": C.BDR_SOFT,
            "borderwidth": 1,
            "font": {"color": C.TEXT_MUTED, "size": 11},
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        "margin": {"l": 10, "r": 10, "t": 20, "b": 10},
    }


def _fig_combined_area(t, ram, cpu, tps, players) -> go.Figure:
    """Gráfico de area combinada con doble eje:
       · Barras/Area = RAM GB + % CPU
       · Linea (eje derecho) = TPS
       · Dots = Players
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t, y=ram,
            name="RAM (GB)", mode="lines", stackgroup=None,
            line={"width": 0.1, "color": C.PLOT_2},
            fill="tozeroy", fillcolor="rgba(184, 149, 106, 0.22)",
            hovertemplate="RAM: %{y:.2f} GB<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t, y=cpu,
            name="CPU (%)", mode="lines",
            line={"width": 2, "shape": "spline", "color": C.PLOT_3},
            fill="tozeroy", fillcolor="rgba(155, 181, 140, 0.14)",
            hovertemplate="CPU: %{y:.1f} %<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t, y=tps,
            name="TPS (eje der.)", mode="lines+markers",
            yaxis="y2",
            line={"width": 2.5, "shape": "spline", "color": C.PLOT_1},
            marker={"size": 4, "color": C.PLOT_1},
            hovertemplate="TPS: %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t, y=players,
            name="Jugadores", mode="markers",
            yaxis="y3",
            marker={"size": 7, "color": C.PLOT_4, "symbol": "circle",
                    "line": {"width": 1, "color": "rgba(0,0,0,0.33)"}},
            hovertemplate="Jugadores: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        **_plotly_theme(),
        xaxis=dict(domain=[0.0, 0.96]),
        yaxis=dict(title="", range=[0, None]),
        yaxis2=dict(
            title="", overlaying="y", side="right",
            range=[0, 21], showgrid=False, showticklabels=True,
            position=0.98,
        ),
        yaxis3=dict(
            title="", overlaying="y", side="right",
            showgrid=False, showticklabels=False, visible=False,
        ),
        height=320,
        hovermode="x unified",
    )
    return fig


def _fig_gauge(value: float, maxv: float, title: str, unit: str, crit=0.7, ok=0.9) -> go.Figure:
    """Medidor circular estilo gauge."""
    pct = max(0.0, min(1.0, float(value or 0) / max(maxv, 0.001)))
    if pct >= ok: color = C.OK
    elif pct >= crit: color = C.WARN
    else: color = C.CRIT

    # Gauge de Plotly realmente
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=float(value or 0),
        number={
            "font": {"color": C.TEXT, "family": "Inter", "size": 26, "weight": 800},
            "suffix": f" {unit}",
        },
        delta={"reference": maxv, "increasing": {"color": C.TEXT_MUTED}},
        domain={"x": [0.1, 0.9], "y": [0.12, 0.92]},
        title={"text": title, "font": {"color": C.TEXT_MUTED, "size": 12, "family": "Inter", "weight": 600}},
        gauge={
            "shape": "angular",
            "bar": {"color": color, "thickness": 0.35},
            "axis": {"range": [0, maxv], "dtick": maxv/5,
                     "tickcolor": C.BDR_SOFT,
                     "tickfont": {"color": C.TEXT_SUBTLE, "size": 10},
                     "linecolor": C.BDR_SOFT},
            "bgcolor": C.BG_SURFACE_2,
            "borderwidth": 1,
            "bordercolor": C.BDR,
            "steps": [
                {"range": [0, maxv * crit], "color": "rgba(194, 125, 113, 0.09)"},
                {"range": [maxv * crit, maxv * ok], "color": "rgba(215, 178, 108, 0.09)"},
                {"range": [maxv * ok, maxv], "color": "rgba(155, 181, 140, 0.12)"},
            ],
            "threshold": {
                "line": {"color": C.ACCENT, "width": 2},
                "thickness": 0.75, "value": float(value or 0),
            },
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=230,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return fig


def _fig_distribution_hist(values: List[float], title: str, unit: str, color: str):
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=values, nbinsx=20,
            marker={"color": color, "line": {"width": 1, "color": "rgba(0,0,0,0.33)"}},
            hovertemplate="Rango: %{x}<br>Frecuencia: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        **_plotly_theme(),
        title={"text": title, "font": {"color": C.TEXT_MUTED, "size": 12, "weight": 600}},
        height=220,
        yaxis_title="Frecuencia",
        xaxis_title=unit,
    )
    return fig


def _fig_timeline_connectivity(t, tps):
    """Linea con fill por debajo; marca cuando el server estuvo debajo de TPS 18."""
    y_colors = [C.OK if v >= 18 else (C.WARN if v >= 10 else C.CRIT) for v in tps]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t, y=tps, mode="lines",
            line={"width": 1.5, "shape": "spline", "color": C.PLOT_1},
            fill="tozeroy", fillcolor="rgba(201, 158, 106, 0.10)",
            hovertemplate="TPS: %{y:.2f}<extra></extra>",
        )
    )
    # Bandas críticas
    fig.add_hrect(y0=0, y1=10, line_width=0, fillcolor="rgba(194, 125, 113, 0.06)", layer="below")
    fig.add_hrect(y0=10, y1=18, line_width=0, fillcolor="rgba(215, 178, 108, 0.05)", layer="below")
    fig.add_hline(y=20, line_width=1, line_dash="dash", line_color=C.TEXT_SUBTLE,
                  annotation_text="20 TPS ideal", annotation_position="top right")
    fig.update_layout(**_plotly_theme(), height=180, showlegend=False,
                      yaxis=dict(range=[0, 21]))
    return fig


def _fig_sparkline(vals: List[float], color: str, height=140) -> go.Figure:
    t = list(range(len(vals)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=vals, mode="lines",
        line={"width": 2, "shape": "spline", "color": color},
        fill="tozeroy", fillcolor=color + "22",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin={"l":0,"r":0,"t":0,"b":0}, height=height, showlegend=False,
    )
    return fig


# ============================================================
# 6. CALCULOS DE METRICAS DERIVADAS
# ============================================================
def calc_derived(state: Dict[str, Any], hist: Dict[str, List[Any]]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    # Valores instantaneos (con fallback a ultimo punto del historial)
    inst = state or {}
    h_ram   = hist.get("hist_ram_gb") or []
    h_cpu   = hist.get("hist_cpu_pct") or []
    h_tps   = hist.get("hist_tps") or []
    h_play  = hist.get("hist_players") or []

    tps_i = float(inst.get("tps") or (h_tps[-1] if h_tps else 0.0))
    ram_i = float(inst.get("ram_gb") or (h_ram[-1] if h_ram else 0.0))
    cpu_i = float(inst.get("cpu_pct") or inst.get("cpu") or (h_cpu[-1] if h_cpu else 0.0))
    pl_i  = int(inst.get("players") or (h_play[-1] if h_play else 0))

    d["tps_i"] = round(tps_i, 2)
    d["ram_i"] = round(ram_i, 2)
    d["cpu_i"] = round(cpu_i, 1)
    d["players_i"] = pl_i

    # MSPT ESTIMADO: 1000ms / TPS - overhead base. Aproximado, util como indicador.
    if tps_i > 0.1:
        mspt_raw = 1000.0 / tps_i
        mspt_raw = max(0.0, mspt_raw - 2.0)
    else:
        mspt_raw = 0.0
    d["mspt_i"] = round(mspt_raw, 2)

    # RAM max heap (asumimos 8 GB por defecto — el NeoForge/Java lo limitó con Xmx)
    RAM_MAX_GB = 8.0
    d["ram_max_gb"] = RAM_MAX_GB
    d["heap_pct"] = round(min(100.0, (ram_i / max(RAM_MAX_GB, 0.001)) * 100.0), 1)

    # Promedios historicos ultimos N puntos
    N = min(30, len(h_tps))
    if N >= 3:
        d["tps_avg30"] = round(float(np.mean(h_tps[-N:])), 2)
        d["cpu_avg30"] = round(float(np.mean(h_cpu[-N:])), 1)
        d["ram_avg30"] = round(float(np.mean(h_ram[-N:])), 2)
        d["tps_p95"]   = round(float(np.percentile(h_tps[-N:], 5)), 2)
        d["players_peak30"] = int(max(h_play[-N:]))
    else:
        d["tps_avg30"] = d["tps_i"]
        d["cpu_avg30"] = d["cpu_i"]
        d["ram_avg30"] = d["ram_i"]
        d["tps_p95"]   = d["tps_i"]
        d["players_peak30"] = d["players_i"]

    # Stability Score (0-100)
    score = 100
    # Penalizaciones por TPS bajo
    if d["tps_i"] < 19: score -= 10
    if d["tps_i"] < 17: score -= 15
    if d["tps_i"] < 14: score -= 20
    if d["tps_i"] < 10: score -= 25
    # Penalizacion CPU alto
    if d["cpu_i"] > 85: score -= 12
    elif d["cpu_i"] > 70: score -= 6
    # Penalizacion heap
    if d["heap_pct"] > 90: score -= 10
    elif d["heap_pct"] > 75: score -= 5
    # Penalizacion volatilidad p95
    diff = d["tps_avg30"] - d["tps_p95"]
    if diff > 4: score -= 8
    if diff > 8: score -= 8
    score = max(0, min(100, score))
    d["stability_score"] = int(score)

    # Uptime (si state tiene timestamp, lo usamos como aprox de tiempo encendido)
    ts = float(inst.get("timestamp") or 0.0)
    if ts:
        age = time.time() - ts
    else:
        age = 0
    # Sino: usamos player_list mc_up "human" del estado
    mc_up_text = str(inst.get("mc_up") or inst.get("uptime") or "")
    d["mc_up_text"] = mc_up_text if 2 < len(mc_up_text) < 80 else "N/A"
    d["age_s"] = int(age)

    # Health Index categorico
    s = d["stability_score"]
    if s >= 85:  d["health_label"], d["health_cls"] = "Excelente", "ok"
    elif s >= 65:d["health_label"], d["health_cls"] = "Estable",   "warn"
    else:        d["health_label"], d["health_cls"] = "Degradado", "crit"

    # Jugadores: parsear lista
    raw_pl = str(inst.get("player_list") or "").strip()
    pl_list: List[str] = []
    if raw_pl and len(raw_pl) > 2 and raw_pl.lower() not in ("none", "[]", "null"):
        # Separadores comunes: , / \n |
        for sep in [",", "|", "\n"]:
            if sep in raw_pl:
                pl_list = [x.strip() for x in raw_pl.split(sep) if x.strip()]
                break
        if not pl_list:
            pl_list = [raw_pl] if len(raw_pl) < 40 else []
    # Sanity check con players_i
    if pl_i > 0 and not pl_list:
        pl_list = [f"Jugador {i+1}" for i in range(min(pl_i, 20))]
    d["player_list"] = pl_list

    return d


# ============================================================
# 7. UI PRINCIPAL
# ============================================================
def ui_status_bar(is_online: bool, age_s: int, pl_count: int, tps: float) -> str:
    if is_online:
        cls = "ok" if tps >= 18 else ("warn" if tps >= 12 else "crit")
        led_cls = "led-on" if tps >= 18 else ("led-warn" if tps >= 12 else "led-off")
        txt = f"<span class='led {led_cls}'></span> <b>SERVIDOR ENCENDIDO</b> · Actualizado hace {max(0,age_s)}s · {pl_count} jugador(es) conectados"
        return pill(cls, txt)
    return pill("crit", f"<span class='led led-off'></span> <b>SERVIDOR APAGADO</b> · Sin señal desde hace {human_uptime(age_s)}")


def ui_hero_bar(is_online: bool):
    ips_html = "  ".join(
        f"<span class='ip-pill'>🌐 {ip} <span style='color:{C.TEXT_SUBTLE}'>·</span> {label}</span>"
        for ip, label in SERVER_IPS
    )
    status_txt = pill("ok",    f"<span class='led led-on'></span>  OPERATIVO") if is_online else \
                 pill("crit",  f"<span class='led led-off'></span>  INACTIVO")
    broker = _get_render_broker_url() or "—"
    st.markdown(
        f"""
        <div class="hero-bar">
          <div>
            <div class="hero-title">🎮 KEO RPG · Monitor del Servidor</div>
            <div class="hero-sub">{status_txt} · <span style='margin-left:8px;'>{ips_html}</span></div>
            <div class="hero-sub" style="margin-top:6px; opacity:0.85;">Broker de datos: <code>{broker}</code> · Auto-refresh cada 30s · Tema Beige/Taupe · Dark Mode</div>
          </div>
          <div class="hero-actions">
             <!-- botones streamlit los renderizamos debajo via st.columns; html placeholder -->
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ui_kpi_card(icon: str, label: str, value: str, sub: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi">
          <div class="kpi-icon">{icon}</div>
          <div style="flex:1; min-width:0;">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {"<div class='kpi-sub'>" + sub + "</div>" if sub else ""}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    # --- Datos listos ---
    is_fresh = (time.time() - float(_GLOBAL_STATE.get("last_push_ts") or 0.0)) <= STALE_THRESHOLD_SECONDS
    payload = _GLOBAL_STATE.get("last_payload") or {}
    hist = {k: list(_GLOBAL_STATE.get(k) or []) for k in ("hist_t", "hist_ram_gb", "hist_cpu_pct", "hist_tps", "hist_players")}
    age_s = int(time.time() - float(_GLOBAL_STATE.get("last_push_ts") or 0.0))

    is_online = bool(is_fresh and payload)
    d = calc_derived(payload if is_online else {}, hist)

    # --- Hero ---
    ui_hero_bar(is_online)

    # Botones funcionales (fila de acciones)
    colB1, colB2, colB3, colB4, colB5 = st.columns([1.2, 1.1, 1.1, 1.0, 2.2])
    with colB1:
        if st.button("📋  Copiar IP del server", use_container_width=True, key="btn_cp_ip"):
            ip_str = "\n".join(f"{ip}  ({label})" for ip, label in SERVER_IPS)
            st.toast("IP copiada al portapapeles (simulado). Copialo manualmente: " + SERVER_IPS[0][0])
    with colB2:
        dash_url = "https://keo-rpg-optimized-server.streamlit.app"
        if st.button("🔗  Copiar Link Dashboard", use_container_width=True, key="btn_cp_link"):
            st.toast("Link: " + dash_url)
    with colB3:
        if st.button("🔄  Forzar Refresh", use_container_width=True, key="btn_refresh"):
            st.rerun()
    with colB4:
        st.markdown(
            ui_status_bar(is_online, age_s, d["players_i"], d["tps_i"]),
            unsafe_allow_html=True,
        )
    with colB5:
        st.markdown("")

    st.markdown(" ")

    # --- Primera fila: 6 KPIs premium ---
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        tps_txt = f"{d['tps_i']:.2f}"
        ui_kpi_card("⚡", "TPS INSTANTÁNEO", tps_txt, f"p95 (30pts): {d['tps_p95']:.2f} · 20 = ideal")
    with k2:
        ui_kpi_card("🧠", "USO RAM", f"{d['ram_i']:.2f} GB",
                    f"Heap Java: {d['heap_pct']}% de {d['ram_max_gb']}GB · avg30={d['ram_avg30']:.2f}GB")
    with k3:
        ui_kpi_card("💻", "CPU HOST", f"{d['cpu_i']:.1f} %",
                    f"avg 30 min: {d['cpu_avg30']:.1f}%")
    with k4:
        ui_kpi_card("🎯", "MSPT ESTIMADO", f"{d['mspt_i']} ms",
                    "Menor es mejor (< 50ms OK)")
    with k5:
        ui_kpi_card("👥", "JUGADORES", f"{d['players_i']}",
                    f"Pico (30pts): {d['players_peak30']}")
    with k6:
        health_color = {"ok": C.OK, "warn": C.WARN, "crit": C.CRIT}[d["health_cls"]]
        ui_kpi_card("🏥", "STABILITY SCORE",
                    f"<span style='color:{health_color};'>{d['stability_score']}/100</span>",
                    f"Estado: {d['health_label']}")

    st.markdown(" ")

    # --- Tabs ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📌  RESUMEN",
        "📊  RENDIMIENTO",
        "👥  JUGADORES",
        "⏱️  HISTORIAL",
        "ℹ️  INFORMACIÓN",
    ])

    # =============================
    # TAB 1 · RESUMEN
    # =============================
    with tab1:
        g1, g2, g3 = st.columns([2.3, 1, 1])
        with g1:
            with st.container(border=True):
                st.markdown("**📈 Rendimiento combinado (últimos puntos)**")
                if hist["hist_t"] and len(hist["hist_t"]) >= 2:
                    fig = _fig_combined_area(
                        hist["hist_t"], hist["hist_ram_gb"],
                        hist["hist_cpu_pct"], hist["hist_tps"], hist["hist_players"],
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Aguardando suficientes datos para graficar (2-3 ciclos de envío).")

        with g2:
            with st.container(border=True):
                st.markdown("**🎚️ Gauge · TPS (0–20)**")
                fig = _fig_gauge(d["tps_i"], 20.0, "Ticks Per Second", "TPS", crit=0.5, ok=0.9)
                st.plotly_chart(fig, use_container_width=True)

        with g3:
            with st.container(border=True):
                st.markdown("**🎚️ Gauge · RAM Heap %**")
                fig = _fig_gauge(d["heap_pct"], 100.0, "Heap Java utilizado", "%",
                                 crit=0.50, ok=0.75)  # ojo invertido: menos es mejor → hay que invertir steps visualmente
                # Re-hacemos el gauge con semántica invertida: menor pct = OK
                pct_r = max(0, min(1, d["heap_pct"]/100))
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=d["heap_pct"],
                    number={"font": {"color": C.TEXT, "family": "Inter", "size": 26, "weight": 800}, "suffix": " %"},
                    domain={"x": [0.1, 0.9], "y": [0.12, 0.92]},
                    title={"text": "Heap Java (%)", "font": {"color": C.TEXT_MUTED, "size": 12, "family": "Inter", "weight": 600}},
                    gauge={
                        "shape": "angular",
                        "bar": {"color": (C.OK if pct_r < 0.65 else (C.WARN if pct_r < 0.85 else C.CRIT)), "thickness": 0.35},
                        "axis": {"range": [0, 100], "tickcolor": C.BDR_SOFT,
                                 "tickfont": {"color": C.TEXT_SUBTLE, "size": 10},
                                 "linecolor": C.BDR_SOFT},
                        "bgcolor": C.BG_SURFACE_2, "borderwidth": 1, "bordercolor": C.BDR,
                        "steps": [
                            {"range": [0, 65],  "color": "rgba(155, 181, 140, 0.12)"},
                            {"range": [65, 85], "color": "rgba(215, 178, 108, 0.10)"},
                            {"range": [85, 100],"color": "rgba(194, 125, 113, 0.11)"},
                        ],
                        "threshold": {"line": {"color": C.ACCENT, "width": 2}, "thickness": 0.75, "value": d["heap_pct"]},
                    },
                ))
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  height=230, margin={"l":10,"r":10,"t":10,"b":10})
                st.plotly_chart(fig, use_container_width=True)

        # --- Segunda fila tab 1: Stability Score detalle + connectivity sparkline + CPU gauge
        r1, r2, r3 = st.columns([1, 1.2, 1])
        with r1:
            with st.container(border=True):
                st.markdown("**🏥 Stability Score breakdown**")
                s = d["stability_score"]
                # Barra horizontal custom
                color = {"ok": C.OK, "warn": C.WARN, "crit": C.CRIT}[d["health_cls"]]
                st.markdown(
                    f"""
                    <div style="font-size:13px;color:{C.TEXT_MUTED};margin-bottom:6px;">Puntuación global de salud del servidor</div>
                    <div style="width:100%;height:16px;background:{C.BG_SURFACE_2};border:1px solid {C.BDR};border-radius:10px;overflow:hidden;">
                      <div style="width:{s}%;height:100%;background:linear-gradient(90deg,{color}CC,{color});"></div>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:12.5px;color:{C.TEXT_MUTED};">
                      <span>0</span><span style="color:{color};font-weight:800;font-size:18px;">{s} / 100</span><span>100</span>
                    </div>
                    """, unsafe_allow_html=True,
                )
                st.markdown(" ")
                st.markdown(
                    f"**{d['health_label']}** — "
                    f"TPS avg30: `{d['tps_avg30']}` · "
                    f"CPU avg30: `{d['cpu_avg30']}%` · "
                    f"Players pico: `{d['players_peak30']}`"
                )

        with r2:
            with st.container(border=True):
                st.markdown("**🔌 Timeline estabilidad TPS**")
                if hist["hist_t"] and len(hist["hist_t"]) >= 2:
                    st.plotly_chart(_fig_timeline_connectivity(hist["hist_t"], hist["hist_tps"]),
                                    use_container_width=True)
                else:
                    st.info("Aguardando datos históricos...")

        with r3:
            with st.container(border=True):
                st.markdown("**🎚️ Gauge · CPU Host %**")
                pct_r = max(0, min(1, d["cpu_i"]/100))
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=d["cpu_i"],
                    number={"font": {"color": C.TEXT, "family": "Inter", "size": 26, "weight": 800}, "suffix": " %"},
                    domain={"x": [0.1, 0.9], "y": [0.12, 0.92]},
                    title={"text": "CPU Host (%)", "font": {"color": C.TEXT_MUTED, "size": 12, "family": "Inter", "weight": 600}},
                    gauge={
                        "shape": "angular",
                        "bar": {"color": (C.OK if pct_r < 0.60 else (C.WARN if pct_r < 0.85 else C.CRIT)), "thickness": 0.35},
                        "axis": {"range": [0, 100], "tickcolor": C.BDR_SOFT,
                                 "tickfont": {"color": C.TEXT_SUBTLE, "size": 10},
                                 "linecolor": C.BDR_SOFT},
                        "bgcolor": C.BG_SURFACE_2, "borderwidth": 1, "bordercolor": C.BDR,
                        "steps": [
                            {"range": [0, 60],  "color": "rgba(155, 181, 140, 0.12)"},
                            {"range": [60, 85], "color": "rgba(215, 178, 108, 0.10)"},
                            {"range": [85, 100],"color": "rgba(194, 125, 113, 0.11)"},
                        ],
                        "threshold": {"line": {"color": C.ACCENT, "width": 2}, "thickness": 0.75, "value": d["cpu_i"]},
                    },
                ))
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  height=230, margin={"l":10,"r":10,"t":10,"b":10})
                st.plotly_chart(fig, use_container_width=True)

    # =============================
    # TAB 2 · RENDIMIENTO
    # =============================
    with tab2:
        st.markdown("#### 🧮 Análisis estadístico de los últimos puntos capturados")
        h1, h2, h3 = st.columns(3)
        with h1:
            with st.container(border=True):
                st.markdown("**Distribución · Uso CPU (%)**")
                if hist["hist_cpu_pct"]:
                    st.plotly_chart(_fig_distribution_hist(hist["hist_cpu_pct"],
                                                           "Histograma CPU Host", "%", C.PLOT_3),
                                    use_container_width=True)
                else:
                    st.info("Sin datos aún...")
        with h2:
            with st.container(border=True):
                st.markdown("**Distribución · Uso RAM (GB)**")
                if hist["hist_ram_gb"]:
                    st.plotly_chart(_fig_distribution_hist(hist["hist_ram_gb"],
                                                           "Histograma RAM Java", "GB", C.PLOT_2),
                                    use_container_width=True)
                else:
                    st.info("Sin datos aún...")
        with h3:
            with st.container(border=True):
                st.markdown("**Distribución · TPS**")
                if hist["hist_tps"]:
                    st.plotly_chart(_fig_distribution_hist(hist["hist_tps"],
                                                           "Histograma TPS", "TPS", C.PLOT_1),
                                    use_container_width=True)
                else:
                    st.info("Sin datos aún...")

        st.markdown(" ")

        t1, t2, t3 = st.columns(3)
        with t1:
            with st.container(border=True):
                st.markdown("**Sparkline · RAM GB**")
                if hist["hist_ram_gb"]:
                    st.plotly_chart(_fig_sparkline(hist["hist_ram_gb"], C.PLOT_2),
                                    use_container_width=True)
                else:
                    st.info("Sin datos.")
        with t2:
            with st.container(border=True):
                st.markdown("**Sparkline · CPU %**")
                if hist["hist_cpu_pct"]:
                    st.plotly_chart(_fig_sparkline(hist["hist_cpu_pct"], C.PLOT_3),
                                    use_container_width=True)
                else:
                    st.info("Sin datos.")
        with t3:
            with st.container(border=True):
                st.markdown("**Sparkline · TPS**")
                if hist["hist_tps"]:
                    st.plotly_chart(_fig_sparkline(hist["hist_tps"], C.PLOT_1),
                                    use_container_width=True)
                else:
                    st.info("Sin datos.")

        st.markdown(" ")

        with st.container(border=True):
            st.markdown("**📋 Tabla de métricas calculadas**")
            rows = [
                ("TPS Instantáneo",        f"{d['tps_i']:.2f}",        "Ticks por segundo. 20 = óptimo"),
                ("TPS avg (30 pts)",       f"{d['tps_avg30']:.2f}",    "Promedio últimos 30 envíos"),
                ("TPS p95 (30 pts)",       f"{d['tps_p95']:.2f}",      "Percentil 5 (cotas bajas, 95% del tiempo > este valor)"),
                ("CPU Host Instantáneo",   f"{d['cpu_i']:.1f} %",      "Carga CPU del host Windows"),
                ("CPU avg (30 pts)",       f"{d['cpu_avg30']:.1f} %",  "Promedio CPU últimos 30 envíos"),
                ("RAM Java Instantáneo",   f"{d['ram_i']:.2f} GB",     "Heap utilizado (aprox Xmx=8GB)"),
                ("RAM avg (30 pts)",       f"{d['ram_avg30']:.2f} GB", "Promedio RAM últimos 30 envíos"),
                ("Heap % Utilizado",       f"{d['heap_pct']} %",       "Contra el máximo de 8GB (Xmx)"),
                ("MSPT Estimado",          f"{d['mspt_i']} ms",        "Milisegundos por tick (≈1000/TPS) — ideal < 50ms"),
                ("Jugadores actuales",     f"{d['players_i']}",        "Conectados AHORA"),
                ("Pico jugadores (30pts)", f"{d['players_peak30']}",   "Máximo en los últimos 30 envios"),
                ("Stability Score",        f"{d['stability_score']}/100", f"Salud general del servidor (0-100)"),
                ("Última señal hace",      f"{max(0, age_s)}s",         "Tiempo desde el último envio del agente"),
                ("Uptime (estimado)",      f"{human_uptime(age_s)}" if is_online else "—",
                                           "Tiempo que lleva enviando señales continuas"),
                ("MC uptime /status",      f"{d['mc_up_text']}",        "Texto crudo del comando /uptime (si RCON funcionó)"),
            ]
            df = pd.DataFrame(rows, columns=["Métrica", "Valor", "Descripción"])
            st.dataframe(df, use_container_width=True, hide_index=True, height=560)

    # =============================
    # TAB 3 · JUGADORES
    # =============================
    with tab3:
        pA, pB = st.columns([1.3, 1])
        with pA:
            with st.container(border=True):
                st.markdown("**👥 Lista de jugadores conectados**")
                if is_online and d["player_list"]:
                    cols = 2
                    for i in range(0, len(d["player_list"]), cols):
                        row_cols = st.columns(cols)
                        for j in range(cols):
                            if i+j < len(d["player_list"]):
                                with row_cols[j]:
                                    name = d["player_list"][i+j]
                                    st.markdown(
                                        f"""
                                        <div class="kpi" style="padding: 10px 12px; margin-bottom:8px;">
                                          <div class="kpi-icon" style="width:34px;height:34px;font-size:15px;">👤</div>
                                          <div style="flex:1;">
                                            <div class="kpi-label">Jugador #{i+j+1}</div>
                                            <div class="kpi-value" style="font-size:17px;">{name}</div>
                                          </div>
                                        </div>
                                        """, unsafe_allow_html=True,
                                    )
                elif is_online and not d["player_list"] and d["players_i"] > 0:
                    st.warning(f"Hay {d['players_i']} jugador(es) conectado(s) pero el agente no pudo obtener los nombres.")
                elif is_online:
                    st.info("Servidor encendido pero sin jugadores conectados en este momento.")
                else:
                    st.error("Servidor apagado. Sin datos de jugadores.")

        with pB:
            with st.container(border=True):
                st.markdown("**📊 Curva de concurrencia (últimos ciclos)**")
                if hist["hist_t"] and len(hist["hist_t"]) >= 2:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=hist["hist_t"], y=hist["hist_players"],
                        mode="lines+markers",
                        line={"width": 2.5, "shape": "spline", "color": C.PLOT_4},
                        marker={"size": 6, "color": C.PLOT_4,
                                "line": {"width": 1, "color": "rgba(0,0,0,0.33)"}},
                        fill="tozeroy", fillcolor="rgba(217, 194, 143, 0.18)",
                        hovertemplate="Jugadores: %{y}<extra></extra>",
                    ))
                    fig.update_layout(**_plotly_theme(), height=300,
                                      yaxis=dict(range=[0, max(5, max(hist["hist_players"])+1)]),
                                      showlegend=False,
                                      yaxis_title="Cantidad de jugadores",
                                      )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Esperando datos de concurrencia...")

            with st.container(border=True):
                st.markdown("**📈 Estadísticas**")
                st.metric("Conectados AHORA", value=f"{d['players_i']}",
                          delta=f"Pico últimos 30 ciclos: {d['players_peak30']}")

    # =============================
    # TAB 4 · HISTORIAL / RAW
    # =============================
    with tab4:
        st.markdown("#### ⏱️ Historial de envíos (últimos puntos capturados)")
        if hist["hist_t"]:
            df_hist = pd.DataFrame({
                "Tiempo": hist["hist_t"],
                "TPS": hist["hist_tps"],
                "RAM (GB)": hist["hist_ram_gb"],
                "CPU (%)": hist["hist_cpu_pct"],
                "Jugadores": hist["hist_players"],
            })
            st.dataframe(df_hist, use_container_width=True, height=520, hide_index=True)
            st.markdown(" ")
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇️  Descargar historial como CSV",
                    data=df_hist.to_csv(index=False).encode("utf-8"),
                    file_name=f"keo-history-{int(time.time())}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c2:
                st.download_button(
                    "⬇️  Descargar historial como JSON",
                    data=json.dumps(df_hist.to_dict(orient="records"), ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name=f"keo-history-{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.info("No hay datos de historial aún. Espera los primeros envíos del agente.")

    # =============================
    # TAB 5 · INFORMACIÓN
    # =============================
    with tab5:
        a, b = st.columns([1.1, 1])
        with a:
            with st.container(border=True):
                st.markdown("**🌐 Direcciones para conectarse al server Minecraft**")
                for ip, label in SERVER_IPS:
                    st.markdown(
                        f"""
                        <div class="kpi" style="padding: 10px 12px; margin-bottom:8px;">
                          <div class="kpi-icon" style="width:34px;height:34px;font-size:15px;">🌐</div>
                          <div style="flex:1;">
                            <div class="kpi-label">{label}</div>
                            <div class="kpi-value" style="font-size:17px; font-family: 'JetBrains Mono', monospace;">{ip}</div>
                          </div>
                        </div>
                        """, unsafe_allow_html=True,
                    )
                st.markdown(" ")
                st.caption("Ambas direcciones apuntan al mismo túnel de Playit.gg TCP (plan gratuito) al puerto de Minecraft.")

        with b:
            with st.container(border=True):
                st.markdown("**🧱 Arquitectura del monitor (sin Playit para la web)**")
                st.markdown(
                    """
                    - **Agente local** (`agent_local.py`): corre en tu PC cuando ejecutas `INICIAR_SERVER.bat`. Captura RAM / CPU / TPS / jugadores cada 10s.
                    - **Broker Render** (`server.py` Flask): intermediario de datos, recibe `POST /api/push` del agente y guarda el último estado + 1000 filas de historial.
                    - **Dashboard Streamlit** (`app.py`): este frontend, lee datos desde el broker con `GET /api/state` y `GET /api/history`.
                    - **Sin puertos raros**, sin HTTPS de pago, sin tuneles HTTP de Playit. Solo 2 links fijos (broker + dashboard).
                    """, unsafe_allow_html=False,
                )
                broker = _get_render_broker_url() or "—"
                st.markdown(
                    f"- **Broker:** `{broker}`\n"
                    f"- **Dashboard público:** `https://keo-rpg-optimized-server.streamlit.app`\n"
                    f"- **Frecuencia de envío:** 10s · **Threshold stale:** {STALE_THRESHOLD_SECONDS}s\n"
                    f"- **Historial máximo guardado en broker:** ~1000 puntos · **Historial mostrado dashboard:** {len(hist['hist_t'])} puntos"
                )

        st.markdown(" ")
        with st.container(border=True):
            st.markdown("**🛠️ Paleta de colores (Tema Beige/Taupe · Dark Mode)**")
            pal = [
                ("BG Deep (fondo)",      C.BG_DEEP,     "Warm black"),
                ("BG Surface (tarjetas)",C.BG_SURFACE,  "Café negro"),
                ("Bordes",               C.BDR,         "Taupe oscuro"),
                ("Texto principal",      C.TEXT,        "Crema claro"),
                ("Texto muted",          C.TEXT_MUTED,  "Taupe medio"),
                ("Accent Bronce",        C.ACCENT,      "CTA principal"),
                ("Accent Soft",          C.ACCENT_SOFT, "Beige luminoso"),
                ("OK (salvia)",          C.OK,          "Verde cálido"),
                ("Warn (beige-amarillo)",C.WARN,        "Warning"),
                ("Crit (terracota)",     C.CRIT,        "Crítico / apagado"),
            ]
            # Render en grid 2xN de tarjetitas
            rows_pal = [pal[i:i+2] for i in range(0, len(pal), 2)]
            for row in rows_pal:
                cols = st.columns(2)
                for idx, item in enumerate(row):
                    name, hex_, desc = item
                    with cols[idx]:
                        st.markdown(
                            f"""
                            <div style="display:flex;gap:10px;align-items:center;
                                        padding:8px 10px;border:1px solid {C.BDR};
                                        border-radius:10px;background:{C.BG_SURFACE_2};">
                              <div style="width:36px;height:36px;border-radius:8px;
                                          background:{hex_};border:1px solid #00000055;"></div>
                              <div style="flex:1;">
                                <div style="color:{C.TEXT};font-weight:700;font-size:13px;">{name}</div>
                                <div style="color:{C.TEXT_MUTED};font-size:11.5px;">
                                  <code>{hex_}</code> · {desc}
                                </div>
                              </div>
                            </div>
                            """, unsafe_allow_html=True,
                        )

    # --- Footer final ---
    st.markdown("---")
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    with fc1:
        st.caption(
            f"🎮 KEO RPG — Monitor del servidor (Premium UI v2) · "
            f"Build: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    with fc2:
        st.caption(
            f"Push totales (sesión): `{int(_GLOBAL_STATE.get('api_push_total') or 0)}` · "
            f"Historial: `{len(hist['hist_t'])}` pts"
        )
    with fc3:
        st.caption(
            f"{'Broker: ON' if _get_render_broker_url() else 'Broker: N/A'} · "
            f"Modo: {'Nube (Render + Streamlit Cloud)' if _get_render_broker_url() else 'Local-File'}"
        )

    # --- Live refresh si hay datos ---
    try:
        if is_online:
            time.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    main()
