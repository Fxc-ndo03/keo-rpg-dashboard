# -*- coding: utf-8 -*-
"""
Servidor Flask para Render.com (Free Tier) — SIN pydantic, SIN Rust.
===================================================================
Este archivo NO corre en tu PC local.
Se sube a GitHub y Render.com lo ejecuta 24/7 GRATIS.

Por qué Flask y no FastAPI:
   FastAPI + pydantic 2.x necesitan compilar pydantic-core con Rust (maturin).
   Render Free Tier tiene el cache de Cargo en read-only. Flask no tiene ningun
   dependencia nativa: instala en 2 segundos y funciona en cualquier Python 3.8+.

Endpoints reales (responden JSON):
  POST /api/push  → recibe stats del agente local (token protegido).
  GET  /api/state → devuelve el estado actual (lo lee Streamlit Cloud).
  GET  /api/history?limit=N → devuelve últimas N filas de histórico para gráficos.
  GET  /          → simple healthcheck con "OK".

Deploy en Render:
  • Runtime: Python 3.11
  • Build Command: pip install -r requirements_render.txt
  • Start Command: gunicorn server:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
"""

from __future__ import annotations

import json
import os
import time
import threading
from collections import deque
from typing import Any

from flask import Flask, jsonify, request

# ============================================================
# CONFIG
# ============================================================
SECRET_TOKEN = str(
    os.environ.get(
        "AGENT_SECRET_TOKEN",
        "keo2026-minecraft-servidor-secreto-123",
    )
).strip()

try:
    MAX_HISTORY = int(str(os.environ.get("MAX_HISTORY", "1000")).strip() or "1000")
except Exception:
    MAX_HISTORY = 1000

# ============================================================
# STATE (en memoria del dyno — Render Free lo reinicia eventualmente,
#        no importa: solo guardamos la sesión actual de stats)
# ============================================================
_LOCK = threading.Lock()
_LAST_STATE: dict[str, Any] | None = None
_HISTORY: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)


# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ============================================================
# ROUTES
# ============================================================
@app.route("/", methods=["GET"])
def root():
    with _LOCK:
        hs = len(_HISTORY)
    return jsonify(
        {
            "status": "ok",
            "service": "keo-rpg-data-broker",
            "has_state": _LAST_STATE is not None,
            "history_rows": hs,
        }
    )


@app.route("/api/push", methods=["POST", "OPTIONS"])
def api_push():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        body = request.get_json(silent=True, force=True) or {}
    except Exception:
        body = {}

    agent_token = str(body.get("agent_token") or "").strip()
    if agent_token != SECRET_TOKEN:
        return (jsonify({"ok": False, "detail": "token invalido"}), 401)

    data = body.get("data")
    if not isinstance(data, dict):
        return (jsonify({"ok": False, "detail": "data debe ser un objeto JSON"}), 400)

    received_at = int(time.time())
    record = dict(data)
    record["_received_at"] = received_at
    if "timestamp" not in record or not isinstance(record["timestamp"], int):
        record["timestamp"] = received_at

    with _LOCK:
        global _LAST_STATE
        _LAST_STATE = record
        _HISTORY.append(record)
        history_rows = len(_HISTORY)

    return jsonify(
        {
            "ok": True,
            "history_rows": history_rows,
            "ts": record["timestamp"],
        }
    )


@app.route("/api/state", methods=["GET", "OPTIONS"])
def api_state():
    if request.method == "OPTIONS":
        return ("", 204)
    with _LOCK:
        st = _LAST_STATE
    if st is None:
        return jsonify({"ok": True, "state": None, "stale": True})
    try:
        age_s = int(time.time()) - int(st.get("timestamp") or st.get("_received_at") or 0)
    except Exception:
        age_s = 0
    return jsonify(
        {
            "ok": True,
            "stale": age_s > 120,
            "age_s": age_s,
            "state": st,
        }
    )


@app.route("/api/history", methods=["GET", "OPTIONS"])
def api_history():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        limit = int(request.args.get("limit", "500"))
    except Exception:
        limit = 500
    limit = max(1, min(limit, MAX_HISTORY))
    with _LOCK:
        rows = list(_HISTORY)[-limit:]
    return jsonify({"ok": True, "count": len(rows), "rows": rows})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
