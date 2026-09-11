# Farmatodo Robot Dashboard

Automatiza la actualización diaria del dashboard del robot autónomo de limpieza,
descargando datos desde Gausium Cloud, procesándolos y regenerando el HTML del
dashboard con los KPIs actualizados.

## Componentes

- `gausium_client.py` — cliente REST para la API de Gausium Cloud (login, tareas, export a Excel, consumibles).
- `data_processor.py` — normaliza los datos crudos y calcula los agregados diarios/mensuales/horarios que consume el dashboard.
- `dashboard_updater.py` — inyecta los datos procesados en el template HTML del dashboard.
- `run_daily.py` — orquesta el pipeline completo: autenticación → descarga → procesamiento → actualización del HTML.
- `config.yaml` — configuración por defecto (credenciales, robot, rutas de archivos, Google Drive, email).
- `.github/workflows/daily_dashboard.yml` — workflow de GitHub Actions que ejecuta el pipeline todos los días.

## Uso

```bash
pip install -r requirements.txt

python run_daily.py                     # Datos de ayer
python run_daily.py --date 2026-08-31    # Fecha específica
python run_daily.py --days 7             # Últimos 7 días
python run_daily.py --full-history       # Reconstruye todo el historial
python run_daily.py --from-file data.xlsx  # Desde un Excel descargado manualmente
```

## Configuración

Completa `config.yaml` o define las siguientes variables de entorno (tienen
prioridad sobre el YAML):

| Variable             | Descripción                                              |
|----------------------|------------------------------------------------------------|
| `GAUSIUM_USERNAME`   | Email o usuario de Gausium Cloud                          |
| `GAUSIUM_PASSWORD`   | Contraseña en texto plano (el script la hashea a MD5)      |
| `ROBOT_SERIAL`       | Número de serie del robot                                  |
| `DASHBOARD_TEMPLATE` | Ruta al HTML template del dashboard (no incluido en este repo) |
| `OUTPUT_PATH`        | Ruta de salida del dashboard actualizado                    |
| `GOOGLE_DRIVE_ID`    | (opcional) ID de carpeta de Google Drive para subir el dashboard |
| `NOTIFY_EMAIL`       | (opcional) destinatario para enviar el dashboard por email  |

El template HTML del dashboard (`dashboard_robot_v11.html` por defecto) debe
colocarse en la raíz del proyecto; no se incluye en este repositorio.

## Automatización

El workflow `.github/workflows/daily_dashboard.yml` corre todos los días a las
6:00 a.m. (hora Colombia) y hace commit del historial y el dashboard
actualizados. Requiere configurar los siguientes secrets en el repositorio:
`GAUSIUM_USERNAME`, `GAUSIUM_PASSWORD`, `ROBOT_SERIAL`, `GOOGLE_DRIVE_ID`,
`NOTIFY_EMAIL`.
