# -*- coding: utf-8 -*-
"""
PLANTILLA de configuracion del agente local — ¡NO EDITAR ESTE ARCHIVO!
Copia este archivo y renombralo a  agent_config.py, luego edita ese.

IMPORTANTE — PLAYIT.GG GRATIS SIN PREMIUM:
  Playit puso "Tunel HTTP" y "HTTPS" en Premium (USD 3/mes).
  SOLUCION GRATUITA: Levanta Streamlit LOCAL (puerto 8501) con
  INICIAR_SERVER.bat y crea un TUNEL TCP (tipo Minecraft) en Playit
  apuntando al puerto 8501. Accede con http://HOST:PUERTO.
  (Pasos completos en INICIAR_SERVER.bat, paso 3b).
"""

# ============================================================
# 🔑 DATOS PRINCIPALES
# ============================================================

# 1. URL del dashboard.
#
#    OPCION A (RECOMENDADA — GRATUITA, SIN PLAYIT PREMIUM):
#    Agente y dashboard corren en LA MISMA PC. El agente escribe
#    directamente a archivos JSON (NO usa HTTP). Deja esta URL tal cual:
DASHBOARD_URL = "http://127.0.0.1:8501"

#    OPCION B (CLOUD — solo si usas Streamlit Community Cloud / Render):
#    Reemplaza por la URL publica de tu deploy (empieza con https://).
#    EJEMPLO:   DASHBOARD_URL = "https://tu-usuario-keo-rpg-dashboard-app-xyz.streamlit.app"
# DASHBOARD_URL = "https://TU-DASHBOARD-AQUI.streamlit.app"


# 2. Token secreto — DEBE ser el MISMO que configuraste en los
#    "Secrets" de Streamlit Community Cloud (o AGENT_SECRET_TOKEN en Render).
#    Ejemplo inventado: keo2026-minecraft-servidor-secreto-123
AGENT_SECRET_TOKEN = "PON-AQUI-TU-TOKEN-SECURITY"


# ============================================================
# 🎮 Conexion RCON (OPCIONAL, para TPS / jugadores 100% reales)
# ============================================================
# Si tenes playit.gg, pon aqui la IP:puerto publico del tunel RCON.
# Si NO tenes RCON publico, dejalo como esta; el agente usara los
# datos que recolecta localmente.
RCON_HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD = ""   # la misma que "rcon.password=" en server.properties


# ============================================================
# ⚙️ Ajustes tecnicos (no tocar a menos que sepas)
# ============================================================
SEND_INTERVAL_SECONDS = 10
REQUEST_TIMEOUT = 8
AGENT_LOG_FILE = "agent_local.log"
LOCAL_MONITOR_DB = r"C:\Users\Admin\Documents\KEO RPG OPTIMIZED SERVER - COPIA\mc_monitor\_monitor_state.json"
JAVA_PROCESS_NAME = ["java.exe", "javaw.exe"]
