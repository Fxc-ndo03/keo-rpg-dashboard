# -*- coding: utf-8 -*-
"""
KEO RPG — Agente Local (Windows)
=================================
Corre en tu PC (donde esta el server Minecraft).
Cada X segundos recolecta:
    - RAM / CPU del proceso Java
    - TPS / jugadores (via RCON si esta, sino via mc_monitor state)

MODO DE FUNCIONAMIENTO RECOMENDADO (GRATIS, SIN PLAYIT PREMIUM):
  • Dashboard Streamlit LANZADO EN LA MISMA PC (puerto 8501, via INICIAR_SERVER.bat)
  • Agente y dashboard se comunican POR ARCHIVOS JSON (NO por HTTP):
      _dashboard_state.json   ← estado actual
      _dashboard_history.jsonl ← historial de 180 puntos
  • Acceso publico: TUNEL TCP en Playit.gg (como Minecraft) al puerto 8501
    → Link: http://TU-HOST.tun.ply.gg:PUERTO  (HTTP, sin HTTPS de pago)

Tambien soporta modo CLOUD (Streamlit Community Cloud / Render) enviando
por HTTP GET al endpoint /?__api_push=1 — mantenido por compatibilidad.

Para correrlo: se lanza SOLO desde INICIAR_SERVER.bat (recomendado).
O manual:  python agent_local.py
"""

from __future__ import annotations

import gc
import json
import re
import sys
import time
import os
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
gc.disable()

# -------- IMPORTS LIGHT --------
try:
    import agent_config as cfg
except ImportError:
    sys.stderr.write(
        "[FATAL] No se pudo importar agent_config. "
        "Asegurate de que agent_config.py exista en la misma carpeta.\n"
    )
    sys.exit(1)

try:
    import psutil
except ImportError:
    sys.stderr.write(
        "[FATAL] Falta 'psutil'. Ejecuta:  pip install psutil requests mcrcon\n"
    )
    sys.exit(2)

try:
    import requests
except ImportError:
    sys.stderr.write("[FATAL] Falta 'requests'.\n")
    sys.exit(2)

_LOG = HERE / cfg.AGENT_LOG_FILE


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ============================================================
# 1. Detector del proceso Java + RAM/CPU
# ============================================================
def _find_java_proc():
    """Devuelve el psutil.Process de java.exe con mayor memoria (server)."""
    best = None
    best_mem = 0
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = (p.info.get("name") or "").lower()
            if name not in cfg.JAVA_PROCESS_NAME:
                continue
            mem = p.info.get("memory_info")
            rss = getattr(mem, "rss", 0) or 0
            if rss > best_mem:
                best_mem = rss
                best = p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return best


_STARTUP_CPU: Dict[int, float] = {}


def _collect_host_stats() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "cpu_pct": 0.0,
        "ram_gb": 0.0,
        "java_pid": None,
        "java_found": False,
    }
    try:
        out["cpu_pct"] = float(psutil.cpu_percent(interval=None) or 0.0)
    except Exception:
        pass
    proc = _find_java_proc()
    if proc is None:
        return out
    try:
        out["java_pid"] = proc.pid
        out["java_found"] = True
        # 1st call to cpu_percent always returns 0, ignore it
        try:
            proc.cpu_percent(interval=None)
        except Exception:
            pass
        mem = proc.memory_info()
        rss = getattr(mem, "rss", 0) or 0
        out["ram_gb"] = round(rss / (1024 ** 3), 2)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return out


# ============================================================
# 2. TPS / Jugadores / Uptime via RCON
# ============================================================
def _rcon_stats() -> Optional[Dict[str, Any]]:
    host = cfg.RCON_HOST
    port = int(cfg.RCON_PORT or 0)
    pwd = str(cfg.RCON_PASSWORD or "").strip()
    if not host or port <= 0 or not pwd:
        return None
    try:
        from mcrcon import MCRcon
    except ImportError:
        return None
    try:
        with MCRcon(host, pwd, port=port, timeout=5) as mcr:
            list_out = mcr.command("list") or ""
            # "There are 2 of a max of 20 players online: Pepe, Juan"
            players = 0
            m_players = __import__("re").search(r"There are\s+(\d+)", list_out)
            if m_players:
                players = int(m_players.group(1))
            player_list = ""
            if ":" in list_out:
                tail = list_out.split(":", 1)[1].strip()
                if tail:
                    player_list = tail

            # Spark / forge TPS? intentamos varios comandos
            tps = 20.0
            for cmd in ("tps", "forge tps", "spark tps", "about"):
                try:
                    r = mcr.command(cmd) or ""
                except Exception:
                    r = ""
                if not r:
                    continue
                m_tps = __import__("re").search(
                    r"(?:Overall|TPS|overall|promedio)[^\d]{0,10}(\d{1,2}(?:\.\d{1,2})?)",
                    r,
                    __import__("re").IGNORECASE,
                )
                if m_tps:
                    try:
                        tps = float(m_tps.group(1))
                        break
                    except Exception:
                        pass

            uptime = ""
            for cmd in ("uptime", "forge uptime"):
                try:
                    r = mcr.command(cmd) or ""
                except Exception:
                    r = ""
                if r and len(r.strip()) < 160:
                    uptime = r.strip().splitlines()[0]
                    break

            return {
                "tps": round(min(20.0, max(0.0, tps)), 2),
                "players": players,
                "player_list": player_list,
                "uptime": uptime,
            }
    except Exception:
        return None


# ============================================================
# 3. Fallback: lee _monitor_state.json de mc_monitor (si existe)
# ============================================================
def _local_state_fallback() -> Dict[str, Any]:
    out = {"tps": 20.0, "players": 0, "player_list": "", "uptime": "", "alerts": 0, "last_msg": ""}
    try:
        p = Path(cfg.LOCAL_MONITOR_DB)
        if not p.exists():
            return out
        with open(p, "r", encoding="utf-8") as f:
            s = json.load(f)
        out["tps"] = float(s.get("tps") or s.get("avg_tps") or 20.0)
        out["players"] = int(s.get("players") or s.get("current_players") or 0)
        out["player_list"] = ",".join(s.get("player_list") or [])
        out["uptime"] = str(s.get("uptime_str") or s.get("mc_up") or "")
        out["alerts"] = int(s.get("alerts_pending") or s.get("alerts") or 0)
        out["last_msg"] = str(s.get("last_alert") or s.get("last_msg") or "")
    except Exception:
        pass
    return out


# ============================================================
# 4. Enviar al dashboard
# ============================================================
def _extract_api_json(text: str) -> Optional[Dict[str, Any]]:
    """Busca el JSON en CUALQUIERA de los formatos empaquetados por el dashboard.
    Orden de busqueda (mas robustos primero):
      1) ===KEO_API_JSON_START=== ... ===KEO_API_JSON_END===
      2) <!-- KEO_JSON_BEGIN --> ... <!-- KEO_JSON_END -->
      3) <script id="keo-api-response" type="application/json">...</script>
      4) ```keojson ... ```
      5) Regex general: {"ok": true|false ... }"""
    if not text:
        return None
    patterns = [
        (r"===KEO_API_JSON_START===\s*(.+?)\s*===KEO_API_JSON_END===", re.DOTALL),
        (r"<!--\s*KEO_JSON_BEGIN\s*-->\s*(.+?)\s*<!--\s*KEO_JSON_END\s*-->", re.DOTALL | re.IGNORECASE),
        (r'<script[^>]*id=["\']keo-api-response["\'][^>]*type=["\']application/json["\'][^>]*>(.+?)</script>', re.DOTALL | re.IGNORECASE),
        (r"```keojson\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE),
    ]
    for pat, flags in patterns:
        try:
            m = re.search(pat, text, flags)
            if m:
                candidate = m.group(1).strip()
                if candidate:
                    return json.loads(candidate)
        except Exception:
            continue
    # Fallback final: busca un objeto JSON que tenga "ok" como primer campo clave
    try:
        m = re.search(r"\{\s*\"ok\"\s*:\s*(?:true|false)[\s\S]*?\}", text)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return None


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Aplana y normaliza el payload a lo que el dashboard/server espera."""
    norm: Dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            norm[k] = v
        elif v is None:
            norm[k] = None
        else:
            norm[k] = v
    try:
        norm["ram_gb"] = round(float(payload.get("ram_gb") or 0), 2)
    except Exception: norm["ram_gb"] = 0.0
    try:
        norm["cpu_pct"] = round(float(payload.get("cpu_pct") or payload.get("cpu") or 0), 1)
    except Exception: norm["cpu_pct"] = 0.0
    try:
        norm["cpu"] = norm["cpu_pct"]
    except Exception: pass
    try:
        norm["tps"] = round(max(0.0, min(20.0, float(payload.get("tps") or 0))), 2)
    except Exception: norm["tps"] = 0.0
    try:
        norm["players"] = int(payload.get("players") or 0)
    except Exception: norm["players"] = 0
    norm["mc_up"] = str(payload.get("uptime") or payload.get("mc_up") or "")[:80]
    try:
        norm["alerts"] = int(payload.get("alerts") or 0)
    except Exception: norm["alerts"] = 0
    norm["last_msg"] = str(payload.get("last_msg") or "")[:250]
    norm["player_list"] = str(payload.get("player_list") or "")[:1000]
    norm["timestamp"] = int(time.time())
    return norm


def _send_to_render(norm_payload: Dict[str, Any]) -> bool:
    """POST al servidor FastAPI broker en Render.com (/api/push).
    Este es el MODO PRINCIPAL 2026: sin Playit, dashboard siempre online.
    """
    base = (getattr(cfg, "RENDER_API_URL", None) or getattr(cfg, "DASHBOARD_URL", "") or "").rstrip("/ ").strip()
    token = (cfg.AGENT_SECRET_TOKEN or "").strip()
    if not base or not token:
        _log("[ENVIO] SKIP — falta RENDER_API_URL o AGENT_SECRET_TOKEN en agent_config.py")
        return False
    if ("CAMBIAR" in base.upper()) or ("CAMBIAR" in token.upper()) or ("TU-" in base.upper()):
        _log("[ENVIO] SKIP — detectado placeholder en agent_config.py. Editalo con tus datos reales.")
        return False

    push_url = base.rstrip("/") + "/api/push"
    try:
        r = requests.post(
            push_url,
            json={"agent_token": token, "data": norm_payload},
            timeout=cfg.REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"Content-Type": "application/json"},
        )
        try:
            parsed = r.json()
        except Exception:
            parsed = None
        if r.status_code == 200 and isinstance(parsed, dict) and parsed.get("ok") is True:
            _log(
                f"[ENVIO OK] tps={norm_payload['tps']:.2f} ram={norm_payload['ram_gb']:.2f}GB "
                f"players={norm_payload['players']} hist_n={parsed.get('history_rows')} [MODO=render-post]"
            )
            return True
        # Render Free puede mandar 503 cuando arranca (sleep) — no loguear como error grave
        if r.status_code in (502, 503, 504, 500):
            _log(f"[ENVIO FALLA] Render HTTP{r.status_code} (dyno dormido, reintentar en proximo ciclo)")
            return False
        msg = ""
        if isinstance(parsed, dict) and parsed.get("detail"):
            msg = str(parsed["detail"])
        elif isinstance(parsed, dict) and parsed.get("msg"):
            msg = str(parsed["msg"])
        _log(f"[ENVIO FALLA] HTTP{r.status_code} {msg}".rstrip())
        if not msg:
            snippet = ""
            try:
                if r.text:
                    snippet = r.text[:400].replace("\r", " ").replace("\n", " ")
            except Exception:
                snippet = ""
            if snippet:
                _log(f"    [Sin JSON detectado]. Primeros chars: {snippet}")
        return False
    except Exception as e:
        _log(f"[ENVIO ERROR] render-post: {type(e).__name__}: {str(e)[:200]}")
        return False


def _send_to_dashboard(payload: Dict[str, Any]) -> bool:
    token = (cfg.AGENT_SECRET_TOKEN or "").strip()
    base = (cfg.DASHBOARD_URL or "").rstrip("/ ").strip()
    if not token:
        _log("[ENVIO] SKIP — falta AGENT_SECRET_TOKEN en agent_config.py")
        return False

    norm_payload = _normalize_payload(payload)

    # ---------------------------------------------------------------
    # PRIORIDAD 1: SI EXISTE RENDER_API_URL → enviamos por POST al broker FastAPI
    #   (modo principal — sin Playit, dashboard siempre online en la nube)
    # ---------------------------------------------------------------
    render_url = (getattr(cfg, "RENDER_API_URL", None) or "").rstrip("/ ").strip()
    if render_url and "CAMBIAR" not in render_url.upper() and "TU-" not in render_url.upper():
        return _send_to_render(norm_payload)

    # ---------------------------------------------------------------
    # PRIORIDAD 2: DASHBOARD LOCAL (Streamlit en la MISMA PC)
    #             → escribimos a archivos JSON compartidos (HTTP no sirve)
    # ---------------------------------------------------------------
    is_localhost = False
    try:
        from urllib.parse import urlparse
        h = (urlparse(base).hostname or "").lower()
        is_localhost = h in ("localhost", "127.0.0.1", "0.0.0.0")
    except Exception:
        is_localhost = base.lower().startswith("http://127.0.0.1") or base.lower().startswith("http://localhost")

    sent_players = f"{norm_payload['players']}"
    sent_tps = f"{norm_payload['tps']:.2f}"
    sent_ram = f"{norm_payload['ram_gb']:.2f}"

    if is_localhost:
        t_sent = time.time()
        web_dir = Path(__file__).resolve().parent
        state_path = web_dir / "_dashboard_state.json"
        history_path = web_dir / "_dashboard_history.jsonl"

        write_error = None
        try:
            state_data = {
                "ok": True,
                "msg": "ok",
                "ts": int(t_sent),
                "ts_float": round(t_sent, 3),
                "last_push_ts": t_sent,
                "last_payload": norm_payload,
                "api_push_total": 0,
                "hist_n": 0,
            }
            counter_path = web_dir / "_dashboard_push_counter.json"
            try:
                if counter_path.exists():
                    counter_data = json.loads(counter_path.read_text(encoding="utf-8"))
                    n = int(counter_data.get("total") or 0) + 1
                else:
                    n = 1
                counter_data = {"total": n, "last_ts": t_sent}
                tmpc = counter_path.with_suffix(".tmp")
                with open(tmpc, "w", encoding="utf-8") as f:
                    json.dump(counter_data, f, ensure_ascii=False, indent=2)
                try:
                    os.replace(tmpc, counter_path)
                except Exception:
                    import shutil as _s; _s.move(str(tmpc), str(counter_path))
                state_data["api_push_total"] = n
            except Exception:
                state_data["api_push_total"] = int(state_data.get("api_push_total") or 0)

            hist_line_obj: Dict[str, Any] = {
                "ts": int(t_sent),
                "t": time.strftime("%H:%M:%S", time.localtime(t_sent)),
                "ram_gb": norm_payload["ram_gb"],
                "cpu_pct": norm_payload["cpu_pct"],
                "tps": norm_payload["tps"],
                "players": norm_payload["players"],
            }
            hist_line_json = json.dumps(hist_line_obj, ensure_ascii=False)
            existing_lines = []
            try:
                if history_path.exists():
                    existing_lines = [ln.rstrip("\r\n") for ln in open(history_path, "r", encoding="utf-8").readlines() if ln.strip()]
            except Exception:
                existing_lines = []
            existing_lines.append(hist_line_json)
            if len(existing_lines) > 180:
                existing_lines = existing_lines[-180:]
            try:
                tmp_h = history_path.with_suffix(".jsonl.tmp")
                with open(tmp_h, "w", encoding="utf-8") as f:
                    f.write("\n".join(existing_lines) + "\n")
                try:
                    os.replace(tmp_h, history_path)
                except Exception:
                    import shutil as _s; _s.move(str(tmp_h), str(history_path))
            except Exception as _he:
                write_error = f"history-write:{type(_he).__name__}"
            state_data["hist_n"] = len(existing_lines)

            tmp_state = state_path.with_suffix(".json.tmp")
            with open(tmp_state, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            try:
                os.replace(tmp_state, state_path)
            except Exception:
                import shutil as _s; _s.move(str(tmp_state), str(state_path))
        except Exception as _e:
            write_error = f"{type(_e).__name__}:{str(_e)[:200]}"

        time.sleep(0.3)
        try:
            if state_path.exists():
                data = json.loads(state_path.read_text(encoding="utf-8"))
                ts_file = float(data.get("ts_float") or data.get("ts") or 0.0)
                age = abs(t_sent - ts_file)
                file_players = str((data.get("last_payload") or {}).get("players", ""))
                if (
                    data.get("ok") is True
                    and age < 12.0
                    and (not file_players or file_players == sent_players)
                ):
                    _log(f"[ENVIO OK] tps={sent_tps} ram={sent_ram}GB players={sent_players} hist={data.get('hist_n')} push_n={data.get('api_push_total')} [MODO=archivo-local]")
                    return True
                _log(f"[ENVIO FALLA] archivo-validation-fail (age={age:.1f}s file_players={file_players} expected_players={sent_players})")
                return False
            _log(f"[ENVIO FALLA] {write_error or 'archivo-no-creado'} [MODO=archivo-local]")
            return False
        except Exception as ex:
            _log(f"[ENVIO ERROR] lectura-archivo-post: {type(ex).__name__} {str(ex)[:200]}")
            return False

    # ---------------------------------------------------------------
    # PRIORIDAD 3: FALLBACK CLOUD HTTP GET (Streamlit Community Cloud).
    #   Este modo NUNCA devuelve JSON — Streamlit no ejecuta app.py en
    #   peticiones HTTP sin WebSocket. Solo se mantiene por compatibilidad
    #   y siempre falla. El usuario tiene que usar RENDER_API_URL.
    # ---------------------------------------------------------------
    if not base:
        _log("[ENVIO] SKIP — falta DASHBOARD_URL en agent_config.py")
        return False
    params = {
        "__api_push": "1",
        "token": token,
        "ram_gb": sent_ram,
        "cpu": f"{norm_payload['cpu_pct']:.1f}",
        "tps": sent_tps,
        "players": sent_players,
        "mc_up": norm_payload["mc_up"],
        "alerts": f"{norm_payload['alerts']}",
        "last_msg": norm_payload["last_msg"],
        "player_list": norm_payload["player_list"],
    }
    try:
        r = requests.get(base + "/", params=params, timeout=cfg.REQUEST_TIMEOUT, allow_redirects=True)
        parsed = _extract_api_json(r.text or "")
        if r.status_code == 200 and parsed and parsed.get("ok") is True:
            _log(f"[ENVIO OK] tps={sent_tps} ram={sent_ram}GB players={sent_players} hist={parsed.get('hist')} [MODO=cloud-http]")
            return True
        _log(
            f"[ENVIO FALLA] HTTP{r.status_code} — Streamlit Cloud NO acepta envios HTTP directos. "
            f"Configura RENDER_API_URL en agent_config.py para usar el broker FastAPI (modo principal)."
        )
        return False
    except Exception as e:
        _log(f"[ENVIO ERROR] cloud-http: {type(e).__name__}: {e}")
        return False


# ============================================================
# 5. Loop principal
# ============================================================
_UPTIME_START = time.time()


def main() -> int:
    _log("=" * 60)
    _log(f"Agente local arrancado. Enviando cada {cfg.SEND_INTERVAL_SECONDS}s a {cfg.DASHBOARD_URL}")
    _log("Presiona Ctrl+C para detener.")
    _log("=" * 60)
    # Primera lectura de CPU (se descarta, es 0 siempre)
    try:
        psutil.cpu_percent(interval=0.1)
    except Exception:
        pass
    # Warmup RCON
    _rcon_stats()

    while True:
        loop_start = time.time()
        try:
            host = _collect_host_stats()
            rcon = _rcon_stats() or {}
            local = _local_state_fallback()
            payload: Dict[str, Any] = {**local, **host, **rcon}
            # Uptime si no tenemos de RCON/local: usamos el tiempo que lleva vivo el agente
            if not payload.get("uptime"):
                s = int(time.time() - _UPTIME_START)
                h, rem = divmod(s, 3600)
                m, s = divmod(rem, 60)
                payload["uptime"] = f"{h:d}h{m:02d}m{s:02d}s"
            _send_to_dashboard(payload)
        except KeyboardInterrupt:
            _log("Detenido por el usuario (Ctrl+C).")
            return 0
        except Exception as e:
            _log(f"[LOOP FATAL] {type(e).__name__}: {e}\n{traceback.format_exc()}")
        finally:
            try:
                gc.collect()
            except Exception:
                pass
        # Sleep ajustado para mantener el intervalo
        elapsed = time.time() - loop_start
        sleep_s = max(0.1, cfg.SEND_INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_s)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
