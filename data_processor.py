#!/usr/bin/env python3
"""
data_processor.py — Procesador de datos de tareas Gausium
==========================================================
Convierte los datos crudos de la API en los arrays JavaScript
que consume el dashboard (DATA, MONTHLY, HOURLY, SQ_TREND).
"""

import json, logging
from datetime import date, datetime
from typing import Any

import pandas as pd

log = logging.getLogger("data_processor")

# Nombres de días en español
DIAS = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']

# Columnas que puede traer la API (JSON) o el Excel descargado
COL_ALIASES = {
    'Task start time':           'Task start time',
    'taskStartTime':             'Task start time',
    'startTime':                 'Task start time',
    'Task status':               'Task status',
    'taskStatus':                'Task status',
    'status':                    'Task status',
    'Actual cleaning area(㎡)':  'm2r',
    'actualCleaningArea':        'm2r',
    'Cleaning plan area (㎡)':   'm2p',
    'cleaningPlanArea':          'm2p',
    'Total time (h)':            'dur',
    'totalTimeH':                'dur',
    'Squeegee(%)':               'sq',
    'squeegeePercent':           'sq',
    'Brush (%)':                 'brush',
    'brushPercent':              'brush',
    'Filter (%)':                'filter',
    'filterPercent':             'filter',
    'Map name':                  'map',
    'mapName':                   'map',
    'S/N':                       'sn',
    'serialNumber':              'sn',
}

STATUS_MAP = {
    'Normal end':           'Normal end',
    'Task replaced':        'Task replaced',
    'Manual termination':   'Manual termination',
    'normalEnd':            'Normal end',
    'taskReplaced':         'Task replaced',
    'manualTermination':    'Manual termination',
    '1': 'Normal end',
    '2': 'Task replaced',
    '3': 'Manual termination',
}

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas y tipos de datos."""
    # Renombrar columnas conocidas
    rename = {k: v for k, v in COL_ALIASES.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Si aún no existe 'm2r', buscar variantes
    for alt in ['Actual cleaning area(?)', 'actual_cleaning_area']:
        if alt in df.columns and 'm2r' not in df.columns:
            df = df.rename(columns={alt: 'm2r'})
    for alt in ['Cleaning plan area (?)', 'cleaning_plan_area']:
        if alt in df.columns and 'm2p' not in df.columns:
            df = df.rename(columns={alt: 'm2p'})

    # Parsear fechas
    df['dt']    = pd.to_datetime(df['Task start time'], errors='coerce')
    df['fecha'] = df['dt'].dt.date
    df['hora']  = df['dt'].dt.hour

    # Normalizar status
    if 'Task status' in df.columns:
        df['Task status'] = df['Task status'].astype(str).map(
            lambda s: STATUS_MAP.get(s.strip(), s.strip())
        )

    # Asegurar tipos numéricos
    for col in ['m2r', 'm2p', 'dur', 'sq', 'brush', 'filter']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df


def aggregate_daily(df: pd.DataFrame) -> list[dict]:
    """Agrupa por día y calcula los KPIs por fecha."""
    df = normalize_df(df)
    df = df.dropna(subset=['fecha'])

    agg = df.sort_values('dt').groupby('fecha').agg(
        tot   = ('Task status', 'count'),
        comp  = ('Task status', lambda x: (x == 'Normal end').sum()),
        repl  = ('Task status', lambda x: (x == 'Task replaced').sum()),
        man   = ('Task status', lambda x: (x == 'Manual termination').sum()),
        m2r   = ('m2r', 'sum'),
        m2p   = ('m2p', 'sum'),
        dur   = ('dur', 'sum'),
        sq    = ('sq',  'last'),
    ).reset_index().sort_values('fecha')

    # Añadir campos derivados
    agg['eff'] = (agg['m2r'] / agg['m2p'] * 100).round(1).clip(upper=100)
    agg['eff'] = agg['eff'].fillna(0)
    agg['wd']  = agg['fecha'].apply(lambda d: DIAS[d.weekday()])
    agg['ds']  = agg['fecha'].apply(lambda d: d.strftime('%d-%b').replace(
        'Jan','Ene').replace('Feb','Feb').replace('Mar','Mar').replace('Apr','Abr')
        .replace('May','May').replace('Jun','Jun').replace('Jul','Jul')
        .replace('Aug','Ago').replace('Sep','Sep').replace('Oct','Oct')
        .replace('Nov','Nov').replace('Dec','Dic'))
    agg['fd']  = agg['fecha'].apply(lambda d: d.strftime('%Y-%m-%d'))
    agg['mes'] = agg['fecha'].apply(lambda d: d.strftime('%Y-%m'))
    agg['st']  = agg['eff'].apply(
        lambda e: 'critical' if e < 30 else ('low' if e < 50 else 'normal'))

    # Tienda / mapa (si está disponible)
    if 'map' in df.columns:
        store_per_day = df.groupby('fecha')['map'].last()
        agg['store'] = agg['fecha'].map(store_per_day).fillna('')
    else:
        agg['store'] = ''

    rows = []
    for _, r in agg.iterrows():
        rows.append({
            'd':    r['ds'],
            'wd':   r['wd'],
            'mes':  r['mes'],
            'fd':   r['fd'],
            'store': str(r['store']),
            'm2r':  round(float(r['m2r']), 0),
            'm2p':  round(float(r['m2p']), 0),
            'tot':  int(r['tot']),
            'comp': int(r['comp']),
            'repl': int(r['repl']),
            'man':  int(r['man']),
            'dur':  round(float(r['dur']), 2),
            'sq':   round(float(r['sq']), 2),
            'eff':  float(r['eff']),
            'st':   r['st'],
        })

    log.info(f"✅ Agregados {len(rows)} días")
    return rows


def build_monthly(daily_rows: list[dict],
                  sq_start_map: dict | None = None) -> list[dict]:
    """Construye el resumen mensual a partir de los datos diarios."""
    from collections import defaultdict

    mes_groups: dict[str, list] = defaultdict(list)
    for r in daily_rows:
        mes_groups[r['mes']].append(r)

    MES_LABELS = {
        '2026-03':'Mar 2026','2026-04':'Abr 2026','2026-05':'May 2026',
        '2026-06':'Jun 2026','2026-07':'Jul 2026','2026-08':'Ago 2026',
        '2026-09':'Sep 2026','2026-10':'Oct 2026','2026-11':'Nov 2026',
        '2026-12':'Dic 2026',
    }
    sq_start_defaults = {
        '2026-03':100.0,'2026-04':82.29,'2026-05':51.24,'2026-06':34.92,
        '2026-07':7.66, '2026-08':5.05,
    }
    if sq_start_map:
        sq_start_defaults.update(sq_start_map)

    monthly = []
    for mk in sorted(mes_groups.keys()):
        rows = mes_groups[mk]
        m2r_ = sum(r['m2r'] for r in rows)
        m2p_ = sum(r['m2p'] for r in rows)
        tot_ = sum(r['tot'] for r in rows)
        comp_= sum(r['comp'] for r in rows)
        monthly.append({
            'mes':      MES_LABELS.get(mk, mk),
            'mk':       mk,
            'dias':     len(rows),
            'tot':      tot_,
            'comp':     comp_,
            'repl':     sum(r['repl'] for r in rows),
            'man':      sum(r['man'] for r in rows),
            'm2r':      round(m2r_, 0),
            'm2p':      round(m2p_, 0),
            'eff':      round(m2r_ / m2p_ * 100, 1) if m2p_ > 0 else 0,
            'pct_comp': round(comp_ / tot_ * 100, 1) if tot_ > 0 else 0,
            'dur':      round(sum(r['dur'] for r in rows), 1),
            'sq_start': sq_start_defaults.get(mk, 0),
            'sq_end':   rows[-1]['sq'],
        })

    return monthly


def build_hourly(df: pd.DataFrame) -> dict:
    """Calcula la distribución horaria de tareas."""
    df = normalize_df(df)
    h = df.groupby('hora').agg(
        comp=('Task status', lambda x: (x == 'Normal end').sum()),
        repl=('Task status', lambda x: (x == 'Task replaced').sum()),
        man =('Task status', lambda x: (x == 'Manual termination').sum()),
    ).reindex(range(24), fill_value=0).reset_index()
    return {
        'comp': h['comp'].tolist(),
        'repl': h['repl'].tolist(),
        'man':  h['man'].tolist(),
    }


def build_sq_trend(daily_rows: list[dict]) -> dict:
    """Construye la tendencia del Squeegee."""
    valid = [r for r in daily_rows if r['sq'] > 0]
    return {
        'labels': [r['d'] for r in valid],
        'values': [r['sq'] for r in valid],
    }
