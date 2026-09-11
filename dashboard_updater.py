#!/usr/bin/env python3
"""
dashboard_updater.py — Actualiza el HTML del dashboard con datos nuevos
=======================================================================
Inyecta los arrays JS (DATA, MONTHLY, HOURLY, SQ_TREND) en el template
HTML del dashboard, generando una versión actualizada lista para compartir.
"""

import json, logging, re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("dashboard_updater")

# Etiqueta de mes para cada mk='2026-XX'
MES_LABELS_ES = {
    '2026-03':'Mar 2026','2026-04':'Abr 2026','2026-05':'May 2026',
    '2026-06':'Jun 2026','2026-07':'Jul 2026','2026-08':'Ago 2026',
    '2026-09':'Sep 2026','2026-10':'Oct 2026','2026-11':'Nov 2026',
    '2026-12':'Dic 2026',
}

class DashboardUpdater:
    """Lee el template HTML y reemplaza los datos JS."""

    def __init__(self, template_path: str = "dashboard_robot_v11.html"):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template no encontrado: {template_path}")
        self.html = self.template_path.read_text(encoding='utf-8')

    # ── REEMPLAZOS DE DATOS ────────────────────────────────────────
    def _replace_js(self, const_name: str, value_js: str):
        """Reemplaza `const NOMBRE=[...]` o `const NOMBRE={...}` en el HTML."""
        pattern = rf'const {const_name}=[\[\{{].*?[\]\}}];'
        new_val  = f'const {const_name}={value_js};'
        self.html, n = re.subn(pattern, new_val, self.html, count=1, flags=re.DOTALL)
        if n == 0:
            log.warning(f"⚠ No se encontró 'const {const_name}' en el template.")
        else:
            log.info(f"  ✅ {const_name} actualizado")

    def update_data(self, daily: list, monthly: list, hourly: dict, sq_trend: dict):
        self._replace_js('DATA',     json.dumps(daily,    ensure_ascii=False))
        self._replace_js('MONTHLY',  json.dumps(monthly,  ensure_ascii=False))
        self._replace_js('HOURLY',   json.dumps(hourly,   ensure_ascii=False))
        self._replace_js('SQ_TREND', json.dumps(sq_trend, ensure_ascii=False))

    # ── METADATOS DEL HEADER ───────────────────────────────────────
    def update_header(self, total_tasks: int, fd_max: str,
                      stores: Optional[list[str]] = None):
        """Actualiza fecha, conteo y tiendas en el encabezado."""
        today = datetime.today().strftime('%d %b %Y')
        fd_date = datetime.strptime(fd_max, '%Y-%m-%d').strftime('%d %b %Y')

        # Fecha actualización
        self.html = re.sub(
            r'Actualizado: \d{2} \w+ \d{4}',
            f'Actualizado: {today}', self.html)

        # Conteo de tareas
        self.html = re.sub(
            r'Gausium Cloud · \d+ tareas[^"]*',
            f'Gausium Cloud · {total_tasks} tareas · Hasta {fd_date}',
            self.html)

        log.info(f"  ✅ Header actualizado ({today}, {total_tasks} tareas)")

    # ── PICKERS DE FECHA ───────────────────────────────────────────
    def update_date_pickers(self, fd_min: str, fd_max: str):
        self.html = re.sub(
            r'min="[^"]*" max="[^"]*"',
            f'min="{fd_min}" max="{fd_max}"',
            self.html)
        # Actualizar valor por defecto del fa-to y cb-to
        self.html = re.sub(
            r'(id="fa-to"[^>]*value=")[^"]*"',
            rf'\g<1>{fd_max}"', self.html)
        self.html = re.sub(
            r'(id="cb-to"[^>]*value=")[^"]*"',
            rf'\g<1>{fd_max}"', self.html)
        log.info(f"  ✅ Date pickers: {fd_min} → {fd_max}")

    # ── MES LABELS EN JS ───────────────────────────────────────────
    def update_mes_labels(self, monthly: list):
        """Regenera el objeto MES_LABEL y la config de mkMesCards."""
        # MES_LABEL
        labels_js = "{" + ",".join(
            f"'{m['mk']}':'{m['mes']}'" for m in monthly) + "}"
        self.html = re.sub(
            r'const MES_LABEL=\{[^}]*\};',
            f'const MES_LABEL={labels_js};',
            self.html)

        # Grid CSS: número de columnas = número de meses
        n = len(monthly)
        self.html = re.sub(
            r'\.mes4\{display:grid;grid-template-columns:repeat\(\d+,1fr\);',
            f'.mes4{{display:grid;grid-template-columns:repeat({n},1fr);',
            self.html)
        log.info(f"  ✅ MES_LABEL actualizado ({n} meses)")

    # ── CONSUMIBLES ────────────────────────────────────────────────
    def update_consumables(self, sq: float, brush: float = 100,
                           filter_: float = 100, corte_date: str = ''):
        """Actualiza las tarjetas de consumibles."""
        sq_pct = f"{sq:.1f}%"
        sq_status = '⛔ CRÍTICO' if sq <= 15 else ('⚠ Bajo' if sq <= 40 else '✔ Normal')

        self.html = re.sub(
            r'<div class="cp c-r">\d+\.\d+%</div>',
            f'<div class="cp c-r">{sq_pct}</div>',
            self.html, count=1)
        if corte_date:
            self.html = re.sub(
                r'Estado de consumibles · Corte \d+ \w+ \d+',
                f'Estado de consumibles · Corte {corte_date}',
                self.html)
        log.info(f"  ✅ Consumibles: Squeegee={sq_pct}")

    # ── GUARDAR ────────────────────────────────────────────────────
    def save(self, output_path: str = "dashboard_robot_latest.html") -> str:
        Path(output_path).write_text(self.html, encoding='utf-8')
        size_kb = Path(output_path).stat().st_size / 1024
        log.info(f"✅ Dashboard guardado → {output_path} ({size_kb:.1f} KB)")
        return output_path
