# Farmatodo Robot Dashboard — Integración Gausium API

Dashboard de operación del robot autónomo de limpieza, alimentado directamente
por el **Gausium Open API** (https://openapi.gs-robot.com, documentado en
https://developer.gs-robot.com).

## ¿Qué hace?

1. `gausium_client.py` se autentica vía OAuth (client credentials) contra el
   Gausium Open API y descarga los reportes de tareas del robot (incluyen el
   estado de consumibles como Squeegee/brush/filter).
2. `data_processor.py` normaliza y agrega esos datos en KPIs diarios/mensuales.
3. `dashboard_updater.py` inyecta esos datos en `dashboard_robot_v11.html`
   (el template del dashboard) y genera `index.html`, un archivo HTML
   autocontenido (sin dependencias externas) listo para abrir, compartir o
   servir como sitio estático.
4. `run_daily.py` orquesta todo el pipeline y mantiene un historial en
   `robot_history.json`.
5. `.github/workflows/daily_dashboard.yml` corre este pipeline todos los días
   automáticamente vía GitHub Actions.

## Configuración

1. Copia la plantilla de configuración:
   ```bash
   cp config.example.yaml config.yaml
   ```
2. Obtén tu **Client ID**, **Client Secret** y **Open Access Key** registrando
   una app en el Developer Portal: https://developer.gs-robot.com (necesitas
   una cuenta con acceso de administrador/integrador en Gausium Cloud; si no
   la tienes, pídesela a tu representante de Gausium). Completa esos valores
   y el número de serie del robot en `config.yaml` **o**, preferiblemente,
   usa variables de entorno (no se versionan):

   | Variable                  | Descripción                                  |
   |---------------------------|-----------------------------------------------|
   | `GAUSIUM_CLIENT_ID`       | Client ID del Developer Portal                |
   | `GAUSIUM_CLIENT_SECRET`   | Client Secret del Developer Portal            |
   | `GAUSIUM_OPEN_ACCESS_KEY` | Open Access Key del Developer Portal          |
   | `ROBOT_SERIAL`            | Número de serie del robot                     |
   | `DASHBOARD_TEMPLATE`      | Template HTML (`dashboard_robot_v11.html`)   |
   | `OUTPUT_PATH`             | Salida del dashboard actualizado              |
   | `GOOGLE_DRIVE_ID`         | (opcional) carpeta de Drive para subir el HTML |
   | `NOTIFY_EMAIL`            | (opcional) destinatario del resumen diario    |

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
`index.html` con los KPIs, el detalle diario, el resumen mensual, la
distribución horaria de tareas y la tendencia de consumibles (Squeegee).

## Automatización (GitHub Actions)

El workflow `.github/workflows/daily_dashboard.yml` corre cada día a las
6:00 a.m. (hora Colombia) y hace commit del dashboard/historial actualizados
(`index.html` y `robot_history.json` **sí se versionan**: así persiste el
historial entre corridas y el dashboard queda servible directamente desde
el repo). Configura estos secretos en el repositorio:

- `GAUSIUM_CLIENT_ID`, `GAUSIUM_CLIENT_SECRET`, `GAUSIUM_OPEN_ACCESS_KEY`, `ROBOT_SERIAL`
- `GOOGLE_DRIVE_ID`, `NOTIFY_EMAIL` (opcionales)

## Dashboard

`dashboard_robot_v11.html` es la plantilla base (con datos vacíos) y sirve
como punto de partida versionado — nunca se sobreescribe. `index.html` es el
resultado generado en cada corrida (arranca como copia vacía de la
plantilla) y sí se versiona, para que Netlify/GitHub Pages lo sirvan tal
cual en la raíz del sitio.

## Publicar en Netlify

El repo ya incluye `netlify.toml` (sin build command, publica la raíz), así
que conectar el sitio es directo:

1. En Netlify: **Add new site → Import an existing project → GitHub** y
   selecciona este repositorio (rama `main` o la que prefieras mantener
   desplegada).
2. Build command: vacío. Publish directory: `.` (ya viene en `netlify.toml`,
   no hace falta tocarlo).
3. Netlify servirá `index.html` en la raíz automáticamente. Al principio
   mostrará el estado vacío ("Sin datos aún") hasta que el workflow de
   GitHub Actions corra por primera vez con las credenciales reales de
   Gausium y haga commit de un `index.html` con datos — Netlify redepliega
   solo con cada push.

El dashboard incluye:
- KPIs (tareas totales, % completadas, eficiencia m², horas de operación,
  estado del Squeegee).
- Filtro por rango de fechas y comparación entre dos periodos.
- Gráfico de distribución horaria de tareas por estado (Normal / Reemplazada
  / Manual) y tendencia del Squeegee.
- Tarjetas de resumen mensual y tabla de detalle diario ordenable.
