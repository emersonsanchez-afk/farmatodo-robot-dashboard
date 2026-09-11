#!/usr/bin/env python3
"""
gausium_client.py — Cliente API para Gausium Cloud
===================================================
Autenticación, descarga de tareas y exportación de reportes.
API Base: https://cloud.gs-robot.com

Documentación Gausium: https://developer.gs-robot.com
"""

import hashlib, logging, time, requests
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger("gausium_client")

class GausiumClient:
    """Cliente para la API REST de Gausium Cloud."""

    BASE = "https://cloud.gs-robot.com"

    # Endpoints conocidos (verificar con tu representante Gausium si cambian)
    ENDPOINTS = {
        "login":        "/api/user/v3/login",
        "robot_list":   "/api/v1/robot/page",
        "task_page":    "/api/v1/robotTask/page",
        "task_export":  "/api/v1/robotTask/export",
        "consumables":  "/api/v1/robot/consumables",
        "robot_status": "/api/v1/robot/status",
    }

    def __init__(self, username: str, password: str, timeout: int = 30):
        self.username = username
        # Gausium espera la contraseña como MD5 en minúsculas
        self.password_md5 = hashlib.md5(password.encode()).hexdigest()
        self.timeout = timeout
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Farmatodo-Robot-Dashboard/1.0",
        })

    # ── AUTENTICACIÓN ──────────────────────────────────────────────
    def login(self) -> bool:
        """Obtiene el token JWT de Gausium Cloud."""
        url = self.BASE + self.ENDPOINTS["login"]
        payload = {
            "account":  self.username,
            "password": self.password_md5,
            "platform": "web",
        }
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                self.token = data["data"]["token"]
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                log.info("✅ Autenticación exitosa en Gausium Cloud.")
                return True
            else:
                log.error(f"❌ Login fallido: {data.get('message', data)}")
                return False

        except requests.RequestException as e:
            log.error(f"❌ Error de conexión al hacer login: {e}")
            return False

    def _ensure_token(self):
        if not self.token:
            if not self.login():
                raise RuntimeError("No se pudo autenticar con Gausium Cloud.")

    # ── CONSULTA DE TAREAS ─────────────────────────────────────────
    def get_tasks(
        self,
        serial_number: str,
        start_date: date,
        end_date: Optional[date] = None,
        page_size: int = 200,
    ) -> list[dict]:
        """
        Descarga todas las tareas del robot para un rango de fechas.

        Args:
            serial_number:  S/N del robot (ej. 'GS438-6260-1CR-7000')
            start_date:     Fecha inicio
            end_date:       Fecha fin (por defecto = start_date)
            page_size:      Resultados por página (máx ~500)

        Returns:
            Lista de dicts con los datos de cada tarea.
        """
        self._ensure_token()
        if end_date is None:
            end_date = start_date

        start_str = f"{start_date} 00:00:00"
        end_str   = f"{end_date} 23:59:59"

        all_tasks = []
        page_num  = 1

        while True:
            params = {
                "pageNum":      page_num,
                "pageSize":     page_size,
                "serialNumber": serial_number,
                "startTime":    start_str,
                "endTime":      end_str,
            }
            url = self.BASE + self.ENDPOINTS["task_page"]
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                body = resp.json()

                if body.get("code") != 0:
                    log.warning(f"Respuesta inesperada en get_tasks: {body.get('message')}")
                    break

                rows  = body["data"].get("list", body["data"].get("records", []))
                total = body["data"].get("total", len(rows))
                all_tasks.extend(rows)

                log.info(f"  Página {page_num}: {len(rows)} tareas | total={total}")

                if len(all_tasks) >= total or len(rows) == 0:
                    break
                page_num += 1
                time.sleep(0.3)  # cortesía a la API

            except requests.RequestException as e:
                log.error(f"Error descargando tareas (página {page_num}): {e}")
                break

        log.info(f"✅ {len(all_tasks)} tareas descargadas ({start_date} → {end_date})")
        return all_tasks

    # ── EXPORTAR EXCEL (igual al que exportas manualmente) ─────────
    def export_excel(
        self,
        serial_number: str,
        start_date: date,
        end_date: Optional[date] = None,
        output_path: str = "TaskReport.xlsx",
    ) -> Optional[str]:
        """
        Descarga el reporte en formato Excel (equivalente a la exportación manual).

        Returns:
            Ruta del archivo descargado, o None si falló.
        """
        self._ensure_token()
        if end_date is None:
            end_date = start_date

        params = {
            "serialNumber": serial_number,
            "startTime":    f"{start_date} 00:00:00",
            "endTime":      f"{end_date} 23:59:59",
            "lang":         "es",
        }
        url = self.BASE + self.ENDPOINTS["task_export"]
        try:
            resp = self.session.get(url, params=params, timeout=60, stream=True)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            log.info(f"✅ Excel descargado → {output_path}")
            return output_path

        except requests.RequestException as e:
            log.error(f"Error exportando Excel: {e}")
            return None

    # ── CONSUMIBLES ────────────────────────────────────────────────
    def get_consumables(self, serial_number: str) -> Optional[dict]:
        """Obtiene el estado actual de consumibles del robot."""
        self._ensure_token()
        url = self.BASE + self.ENDPOINTS["consumables"]
        try:
            resp = self.session.get(url, params={"serialNumber": serial_number},
                                    timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == 0:
                return body["data"]
        except requests.RequestException as e:
            log.error(f"Error obteniendo consumibles: {e}")
        return None

    # ── ESTADO DEL ROBOT ───────────────────────────────────────────
    def get_robot_status(self, serial_number: str) -> Optional[dict]:
        """Obtiene el estado actual del robot (online/offline, batería, etc.)."""
        self._ensure_token()
        url = self.BASE + self.ENDPOINTS["robot_status"]
        try:
            resp = self.session.get(url, params={"serialNumber": serial_number},
                                    timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == 0:
                return body["data"]
        except requests.RequestException as e:
            log.error(f"Error obteniendo estado del robot: {e}")
        return None
