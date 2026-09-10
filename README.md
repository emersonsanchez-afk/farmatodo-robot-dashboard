# Farmatodo Robot Dashboard — Integración Gausium API

Dashboard de operación del robot autónomo de limpieza, alimentado directamente
por la API de **Gausium Cloud** (https://cloud.gausium.com).

## ¿Qué hace?

1. `gausium_client.py` se autentica contra Gausium Cloud y descarga las tareas
   del robot (por API JSON o exportación Excel) y el estado de consumibles.
2. `data_processor.py` normaliza y agrega esos datos en KPIs diarios/mensuales.
3. `dashboard_updater.py` inyecta esos datos en `dashboard_robot_v11.html`
   (el template del dashboard) y genera `dashboard_robot_latest.html`, un
   archivo HTML autocontenido (sin dependencias externas) listo para abrir o
   compartir.
4. `run_daily.py` orquesta todo el pipeline y mantiene un historial en
   `robot_history.json`.
5. `.github/workflows/daily_dashboard.yml` corre este pipeline todos los días
   automáticamente vía GitHub Actions.

## Configuración

1. Copia la plantilla de configuración:
   ```bash
   cp config.example.yaml config.yaml
   ```
2. Completa tus credenciales de `cloud.gausium.com` y el número de serie del
   robot en `config.yaml` **o**, preferiblemente, usa variables de entorno
   (no se versionan):

   | Variable             | Descripción                                  |
   |----------------------|-----------------------------------------------|
   | `GAUSIUM_USERNAME`   | Email/usuario del portal Gausium Cloud       |
   | `GAUSIUM_PASSWORD`   | Contraseña (se hashea a MD5 antes de enviarla) |
   | `ROBOT_SERIAL`       | Número de serie del robot                     |
   | `DASHBOARD_TEMPLATE` | Template HTML (`dashboard_robot_v11.html`)   |
   | `OUTPUT_PATH`        | Salida del dashboard actualizado              |
   | `GOOGLE_DRIVE_ID`    | (opcional) carpeta de Drive para subir el HTML |
   | `NOTIFY_EMAIL`       | (opcional) destinatario del resumen diario    |

   `config.yaml` está en `.gitignore` para evitar subir credenciales por error.

3. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

```bash
python run_daily.py                     # Datos de ayer
python run_daily.py --date 2026-08-31   # Fecha específica
python run_daily.py --days 7            # Últimos 7 días
python run_daily.py --full-history      # Reconstruye todo el historial
python run_daily.py --from-file data.xlsx  # Desde un Excel/CSV local (sin API)
```

Cada corrida actualiza `robot_history.json` (historial acumulado) y regenera
`dashboard_robot_latest.html` con los KPIs, el detalle diario, el resumen
mensual, la distribución horaria de tareas y la tendencia de consumibles
(Squeegee).

## Automatización (GitHub Actions)

El workflow `.github/workflows/daily_dashboard.yml` corre cada día a las
6:00 a.m. (hora Colombia) y hace commit del dashboard/historial actualizados.
Configura estos secretos en el repositorio:

- `GAUSIUM_USERNAME`, `GAUSIUM_PASSWORD`, `ROBOT_SERIAL`
- `GOOGLE_DRIVE_ID`, `NOTIFY_EMAIL` (opcionales)

## Dashboard

`dashboard_robot_v11.html` es la plantilla base (con datos vacíos) y sirve
como punto de partida versionado. `dashboard_robot_latest.html` es el
resultado generado en cada corrida y **no se versiona** (ver `.gitignore`);
se sube como artefacto de la corrida de GitHub Actions y opcionalmente a
Google Drive o por correo.

El dashboard incluye:
- KPIs (tareas totales, % completadas, eficiencia m², horas de operación,
  estado del Squeegee).
- Filtro por rango de fechas y comparación entre dos periodos.
- Gráfico de distribución horaria de tareas por estado (Normal / Reemplazada
  / Manual) y tendencia del Squeegee.
- Tarjetas de resumen mensual y tabla de detalle diario ordenable.
