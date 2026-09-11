#!/usr/bin/env python3
"""
run_daily.py — Script principal de actualización diaria del dashboard
=====================================================================
Orquesta: autenticación → descarga → procesamiento → actualización HTML.

USO:
  python run_daily.py                     # Actualiza con datos de ayer
  python run_daily.py --date 2026-08-31   # Fecha específica
  python run_daily.py --days 7            # Últimos 7 días
  python run_daily.py --full-history      # Reconstruye desde cero (carga lenta)
  python run_daily.py --from-file data.xlsx  # Desde un Excel descargado manualmente

VARIABLES DE ENTORNO (o en config.yaml):
  GAUSIUM_USERNAME   email o usuario de Gausium Cloud
  GAUSIUM_PASSWORD   contraseña (en texto plano; el script la hashea)
  ROBOT_SERIAL       número de serie del robot
  DASHBOARD_TEMPLATE ruta al HTML template del dashboard
  OUTPUT_PATH        ruta de salida del dashboard actualizado
  GOOGLE_DRIVE_ID    (opcional) ID de carpeta para subir a Google Drive
  NOTIFY_EMAIL       (opcional) destinatario para enviar el dashboard por email
"""

import os, sys, json, logging, argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('robot_dashboard.log', encoding='utf-8'),
    ]
)
log = logging.getLogger('run_daily')

# ── Módulos locales ────────────────────────────────────────────────
from gausium_client   import GausiumClient
from data_processor   import (aggregate_daily, build_monthly,
                               build_hourly, build_sq_trend, normalize_df)
from dashboard_updater import DashboardUpdater


# ── CONFIGURACIÓN ──────────────────────────────────────────────────
def load_config(config_file: str = 'config.yaml') -> dict:
    """Carga config desde YAML, con fallback a variables de entorno."""
    cfg = {}
    config_path = Path(config_file)
    if not config_path.exists() and config_file == 'config.yaml':
        # config.yaml es local y no se versiona; usa config.example.yaml como referencia
        example = Path('config.example.yaml')
        if example.exists():
            config_path = example
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

    # Variables de entorno tienen prioridad sobre el YAML
    cfg['username']     = os.getenv('GAUSIUM_USERNAME',  cfg.get('username', ''))
    cfg['password']     = os.getenv('GAUSIUM_PASSWORD',  cfg.get('password', ''))
    cfg['robot_serial'] = os.getenv('ROBOT_SERIAL',      cfg.get('robot_serial', 'GS438-6260-1CR-7000'))
    cfg['template']     = os.getenv('DASHBOARD_TEMPLATE', cfg.get('template', 'dashboard_robot_v11.html'))
    cfg['output']       = os.getenv('OUTPUT_PATH',        cfg.get('output', 'index.html'))
    cfg['drive_folder'] = os.getenv('GOOGLE_DRIVE_ID',    cfg.get('drive_folder', ''))
    cfg['notify_email'] = os.getenv('NOTIFY_EMAIL',       cfg.get('notify_email', ''))
    cfg['history_file'] = cfg.get('history_file', 'robot_history.json')
    return cfg


# ── HISTORIAL LOCAL ────────────────────────────────────────────────
def load_history(path: str) -> list:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return []

def save_history(data: list, path: str):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Historial guardado: {len(data)} días → {path}")


def merge_daily(existing: list, new_rows: list) -> list:
    """Combina historial existente con nuevos datos, reemplazando días duplicados."""
    existing_by_fd = {r['fd']: r for r in existing}
    for r in new_rows:
        existing_by_fd[r['fd']] = r  # sobreescribe si ya existe
    return sorted(existing_by_fd.values(), key=lambda r: r['fd'])


# ── GOOGLE DRIVE (opcional) ────────────────────────────────────────
def upload_to_drive(file_path: str, folder_id: str):
    """Sube el dashboard a Google Drive. Requiere google-api-python-client."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            'service_account.json',
            scopes=['https://www.googleapis.com/auth/drive.file'])
        drive = build('drive', 'v3', credentials=creds)

        meta = {'name': Path(file_path).name, 'parents': [folder_id]}
        media = MediaFileUpload(file_path, mimetype='text/html')
        drive.files().create(body=meta, media_body=media, fields='id').execute()
        log.info(f"☁️  Subido a Google Drive (carpeta: {folder_id})")
    except Exception as e:
        log.warning(f"Google Drive no disponible: {e}")


# ── NOTIFICACIÓN POR EMAIL (opcional) ─────────────────────────────
def send_email_notification(output_path: str, email: str, daily_summary: dict):
    """Envía el dashboard por email. Requiere configurar SMTP en config.yaml."""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        cfg = load_config()
        smtp_cfg = cfg.get('smtp', {})
        if not smtp_cfg:
            return

        msg = MIMEMultipart()
        msg['From']    = smtp_cfg['from']
        msg['To']      = email
        msg['Subject'] = f"📊 Dashboard Robot Farmatodo — {datetime.today().strftime('%d/%m/%Y')}"

        body = f"""
Buenos días,

Se adjunta el dashboard actualizado del robot autónomo de limpieza.

Resumen del día:
• Tareas completadas: {daily_summary.get('comp', '—')}/{daily_summary.get('tot', '—')}
• Eficiencia m²: {daily_summary.get('eff', '—')}%
• Horas de operación: {daily_summary.get('dur', '—')} h
• Squeegee: {daily_summary.get('sq', '—')}%

Farmatodo Colombia S.A. · Dirección de Operaciones · Proyecto ADT 2.0
        """.strip()

        msg.attach(MIMEText(body, 'plain'))

        with open(output_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                         f'attachment; filename="{Path(output_path).name}"')
        msg.attach(part)

        with smtplib.SMTP(smtp_cfg['host'], smtp_cfg.get('port', 587)) as server:
            server.starttls()
            server.login(smtp_cfg['user'], smtp_cfg['pass'])
            server.sendmail(smtp_cfg['from'], email, msg.as_string())

        log.info(f"📧 Dashboard enviado a {email}")
    except Exception as e:
        log.warning(f"Email no enviado: {e}")


# ── PIPELINE PRINCIPAL ─────────────────────────────────────────────
def run(cfg: dict, args: argparse.Namespace):
    log.info("=" * 60)
    log.info("🤖 FARMATODO ROBOT — Actualización Dashboard")
    log.info("=" * 60)

    # 1 · Determinar rango de fechas
    today = date.today()
    if args.date:
        target = date.fromisoformat(args.date)
        start, end = target, target
    elif args.days:
        start = today - timedelta(days=args.days)
        end   = today - timedelta(days=1)
    elif args.full_history:
        start = date(2026, 3, 11)  # primera fecha del dataset
        end   = today - timedelta(days=1)
    else:
        # Modo normal: datos de ayer
        start = today - timedelta(days=1)
        end   = today - timedelta(days=1)

    log.info(f"📅 Rango: {start} → {end}")

    # 2 · Cargar historial existente
    existing = load_history(cfg['history_file'])
    log.info(f"📂 Historial existente: {len(existing)} días")

    # 3 · Obtener nuevos datos
    new_df = pd.DataFrame()

    if args.from_file:
        # Modo offline: leer desde Excel/CSV
        log.info(f"📁 Cargando desde archivo: {args.from_file}")
        p = args.from_file
        if p.endswith('.csv'):
            sep = ';' if open(p).read(500).count(';') > open(p).read(500).count(',') else ','
            new_df = pd.read_csv(p, sep=sep)
        else:
            new_df = pd.read_excel(p)

    elif cfg['username'] and cfg['password']:
        # Modo online: descargar de la API
        client = GausiumClient(cfg['username'], cfg['password'])
        if not client.login():
            log.error("❌ No se pudo autenticar. Verifica tus credenciales en config.yaml")
            sys.exit(1)

        # Intentar exportación Excel directa (más completa)
        tmp_xlsx = f"_tmp_tasks_{start}_{end}.xlsx"
        excel_path = client.export_excel(cfg['robot_serial'], start, end, tmp_xlsx)

        if excel_path:
            new_df = pd.read_excel(excel_path)
            Path(excel_path).unlink(missing_ok=True)  # limpiar temporal
        else:
            # Fallback: API de tareas JSON
            log.info("⚠ Excel no disponible, usando API de tareas JSON...")
            tasks = client.get_tasks(cfg['robot_serial'], start, end)
            new_df = pd.DataFrame(tasks) if tasks else pd.DataFrame()

        # Consumibles (si disponible)
        consumables = client.get_consumables(cfg['robot_serial'])
        if consumables:
            log.info(f"🔧 Consumibles: Squeegee={consumables.get('squeegeePercent','—')}% "
                     f"Brush={consumables.get('brushPercent','—')}%")

    else:
        log.error("❌ Sin credenciales API ni archivo. Usa --from-file o configura config.yaml")
        sys.exit(1)

    # 4 · Procesar datos nuevos
    if new_df.empty:
        log.warning("⚠ Sin datos nuevos para el rango solicitado.")
        new_rows = []
    else:
        new_rows = aggregate_daily(new_df)
        log.info(f"📊 {len(new_rows)} días procesados: " +
                 ", ".join(f"{r['fd']}({r['eff']}%)" for r in new_rows))

    # 5 · Fusionar con historial
    all_daily = merge_daily(existing, new_rows)
    save_history(all_daily, cfg['history_file'])

    # 6 · Reconstruir arrays para el dashboard
    monthly  = build_monthly(all_daily)
    sq_trend = build_sq_trend(all_daily)

    # Hourly: recalcular desde el DataFrame completo
    if not new_df.empty:
        hourly = build_hourly(new_df)
    else:
        hourly = {'comp':[0]*24, 'repl':[0]*24, 'man':[0]*24}

    # 7 · Actualizar el dashboard
    log.info(f"\n🖥  Actualizando dashboard → {cfg['output']}")
    updater = DashboardUpdater(cfg['template'])
    updater.update_data(all_daily, monthly, hourly, sq_trend)

    fd_min = all_daily[0]['fd']  if all_daily else str(start)
    fd_max = all_daily[-1]['fd'] if all_daily else str(end)
    updater.update_date_pickers(fd_min, fd_max)
    updater.update_header(sum(r['tot'] for r in all_daily), fd_max)
    updater.update_mes_labels(monthly)

    if all_daily:
        last = all_daily[-1]
        corte_fmt = datetime.strptime(fd_max, '%Y-%m-%d').strftime('%d %b %Y')
        updater.update_consumables(last['sq'], corte_date=corte_fmt)

    output = updater.save(cfg['output'])

    # 8 · Acciones opcionales post-generación
    if cfg['drive_folder']:
        upload_to_drive(output, cfg['drive_folder'])

    if cfg['notify_email'] and new_rows:
        send_email_notification(output, cfg['notify_email'], new_rows[-1])

    # 9 · Resumen
    log.info("\n" + "=" * 60)
    log.info("✅ ACTUALIZACIÓN COMPLETA")
    log.info(f"   Dashboard: {output}")
    log.info(f"   Período:   {fd_min} → {fd_max}")
    log.info(f"   Días:      {len(all_daily)}")
    log.info(f"   Tareas:    {sum(r['tot'] for r in all_daily)}")
    log.info("=" * 60)


# ── ENTRY POINT ────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Actualiza el dashboard del robot Farmatodo.')
    parser.add_argument('--date',         help='Fecha específica (YYYY-MM-DD)')
    parser.add_argument('--days',         type=int, help='Últimos N días')
    parser.add_argument('--full-history', action='store_true', help='Reconstruir todo el historial')
    parser.add_argument('--from-file',    help='Cargar datos desde un Excel o CSV local')
    parser.add_argument('--config',       default='config.yaml', help='Archivo de configuración')
    args = parser.parse_args()

    cfg = load_config(args.config)
    run(cfg, args)
