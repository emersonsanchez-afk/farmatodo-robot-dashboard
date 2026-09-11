#!/usr/bin/env python3
"""
gausium_client.py — Cliente del Gausium Open API
==================================================
Autenticación OAuth y descarga de reportes de tareas del robot.
API Base: https://openapi.gs-robot.com

Documentación oficial: https://developer.gs-robot.com
(portal para obtener Client ID / Client Secret / Open Access Key)
"""

import logging, time, requests
from datetime import date, datetime
from typing import Optional

log = logging.getLogger("gausium_client")

# Gausium usa 4 estados de finalización de tarea; los mapeamos a las 3
# categorías que consume el dashboard (Normal / Reemplazada / Manual).
TASK_END_STATUS = {
    0:  "Normal end",           # finalización normal
    1:  "Manual termination",   # detenida por un humano
    2:  "Task replaced",        # detenida por una falla del robot
    3:  "Task replaced",        # otro motivo
    -1: "Task replaced",        # desconocido
}


class GausiumClient:
    """Cliente para el Gausium Open API (OAuth2 client-credentials)."""

    BASE = "https://openapi.gs-robot.com"

    ENDPOINTS = {
        "oauth_token":  "/gas/api/v1alpha1/oauth/token",
        "robot_status": "/v1alpha1/robots/{sn}/status",
        "task_reports": "/openapi/v2alpha1/robots/{sn}/taskReports",
    }

    def __init__(self, client_id: str, client_secret: str, open_access_key: str,
                 timeout: int = 30):
        self.client_id = client_id
        self.client_secret = client_secret
        self.open_access_key = open_access_key
        self.timeout = timeout
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Farmatodo-Robot-Dashboard/1.0",
        })

    # ── AUTENTICACIÓN (OAuth2) ──────────────────────────────────────
    def login(self) -> bool:
        """Obtiene el access token OAuth del Gausium Open API."""
        url = self.BASE + self.ENDPOINTS["oauth_token"]
        payload = {
            "grant_type": "urn:gaussian:params:oauth:grant-type:open-access-token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "open_access_key": self.open_access_key,
        }
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            token = data.get("access_token")
            if not token:
                log.error(f"❌ Login fallido: respuesta sin access_token: {data}")
                return False

            self.token = token
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            log.info("✅ Autenticación exitosa en Gausium Open API.")
            return True

        except requests.RequestException as e:
            log.error(f"❌ Error de conexión al hacer login: {e}")
            return False

    def _ensure_token(self):
        if not self.token:
            if not self.login():
                raise RuntimeError("No se pudo autenticar con el Gausium Open API.")

    # ── CONSULTA DE TAREAS ─────────────────────────────────────────
    def get_tasks(
        self,
        serial_number: str,
        start_date: date,
        end_date: Optional[date] = None,
        page_size: int = 100,
    ) -> list[dict]:
        """
        Descarga todos los reportes de tareas del robot para un rango de
        fechas, ya normalizados a las columnas que espera data_processor.py.

        Args:
            serial_number:  S/N del robot (ej. 'GS438-6260-1CR-7000')
            start_date:     Fecha inicio
            end_date:       Fecha fin (por defecto = start_date)
            page_size:      Resultados por página

        Returns:
            Lista de dicts con los datos de cada tarea.
        """
        self._ensure_token()
        if end_date is None:
            end_date = start_date

        start_str = f"{start_date}T00:00:00Z"
        end_str   = f"{end_date}T23:59:59Z"

        all_tasks: list[dict] = []
        page = 1
        url = self.BASE + self.ENDPOINTS["task_reports"].format(sn=serial_number)

        while True:
            params = {
                "page": page,
                "pageSize": page_size,
                "startTimeUtcFloor": start_str,
                "startTimeUtcUpper": end_str,
            }
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                body = resp.json()

                reports = body.get("robotTaskReports", [])
                total = int(body.get("total", len(reports)) or 0)
                all_tasks.extend(self._normalize_report(r) for r in reports)

                log.info(f"  Página {page}: {len(reports)} tareas | total={total}")

                if len(all_tasks) >= total or len(reports) == 0:
                    break
                page += 1
                time.sleep(0.3)  # cortesía a la API

            except requests.RequestException as e:
                log.error(f"Error descargando tareas (página {page}): {e}")
                break

        log.info(f"✅ {len(all_tasks)} tareas descargadas ({start_date} → {end_date})")
        return all_tasks

    @staticmethod
    def _normalize_report(r: dict) -> dict:
        """Aplana un robotTaskReport crudo a las columnas de data_processor.py."""
        consumables = r.get("consumablesResidualPercentage") or {}
        subtasks = r.get("subTasks") or []
        map_name = subtasks[0].get("mapName") if subtasks else r.get("areaNameList", "")
        duration_s = r.get("durationSeconds") or 0

        return {
            "Task start time": r.get("startTime"),
            "Task status": TASK_END_STATUS.get(r.get("taskEndStatus"), "Manual termination"),
            "m2r": r.get("actualCleaningAreaSquareMeter", 0),
            "m2p": r.get("plannedCleaningAreaSquareMeter", 0),
            "dur": duration_s / 3600.0,
            # "suctionBlade" es el nombre técnico del Squeegee (cauchillo de secado)
            "sq": consumables.get("suctionBlade", 0),
            "brush": consumables.get("brush", 0),
            "filter": consumables.get("filter", 0),
            "map": map_name or "",
        }

    # ── ESTADO DEL ROBOT ───────────────────────────────────────────
    def get_robot_status(self, serial_number: str) -> Optional[dict]:
        """Obtiene el estado actual del robot (online/offline, batería, etc.)."""
        self._ensure_token()
        url = self.BASE + self.ENDPOINTS["robot_status"].format(sn=serial_number)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.error(f"Error obteniendo estado del robot: {e}")
        return None
