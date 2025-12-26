import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_PATH = 'historico_cartas.db'

def inicializar_bd():
    """
    Inicializa la base de datos SQLite con tabla precios_cartas.
    - Agrega UNIQUE constraint en (nombre, fecha, timestamp) para evitar duplicados.
    - Cambia timestamp a tipo DATETIME (afinidad en SQLite; almacenamos como ISO string).
    - Nota: Si la tabla existe, la recrea para aplicar cambios (backup manual recomendado).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Recrear tabla para aplicar cambios (en prod, usa ALTER o migración)
    cursor.execute("DROP TABLE IF EXISTS precios_cartas")
    
    # Nueva estructura: timestamp como DATETIME (almacenamos full datetime)
    cursor.execute("""
        CREATE TABLE precios_cartas (
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            fecha TEXT NOT NULL,  -- YYYY-MM-DD (mantenemos para compatibilidad)
            timestamp DATETIME NOT NULL,  -- Full: YYYY-MM-DD HH:MM:SS (nuevo tipo)
            wishlist_id INTEGER NOT NULL,
            UNIQUE(nombre, fecha, timestamp)  -- Evita dups exactos
        )
    """)
    
    # Índices para queries rápidas
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_fecha ON precios_cartas(wishlist_id, fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nombre_fecha ON precios_cartas(nombre, fecha)")
    
    conn.commit()
    conn.close()
    print(f"[INFO] BD inicializada en {DB_PATH} con constraints y DATETIME.")

def guardar_historial(cartas, wishlist_id):
    """
    Guarda el histórico de precios en batch, solo si precio cambió (>0.01€).
    - Usa full datetime para timestamp.
    - Retorna número de filas insertadas (para condicional en export).
    """
    if not cartas:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted_count = 0
    inserts = []
    now = datetime.now()
    fecha = now.strftime("%Y-%m-%d")
    timestamp_full = now.strftime("%Y-%m-%d %H:%M:%S")  # ISO para DATETIME
    
    for carta in cartas:
        nombre = carta['Nombre']
        precio = float(carta['Precio'])
        
        # Check si ya existe con mismo precio (último timestamp)
        cursor.execute("""
            SELECT precio FROM precios_cartas 
            WHERE nombre = ? AND fecha = ? AND wishlist_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        """, (nombre, fecha, wishlist_id))
        last_precio = cursor.fetchone()
        
        if last_precio is None or abs(last_precio[0] - precio) > 0.01:
            # Insert solo si nuevo o cambió
            inserts.append((nombre, precio, fecha, timestamp_full, wishlist_id))
            inserted_count += 1
    
    if inserts:
        cursor.executemany("""
            INSERT INTO precios_cartas (nombre, precio, fecha, timestamp, wishlist_id)
            VALUES (?, ?, ?, ?, ?)
        """, inserts)
        conn.commit()
        print(f"[INFO] Insertadas {len(inserts)} nuevas/updates para wishlist {wishlist_id}.")
    
    conn.close()
    return inserted_count  # Retorna para condicional

def get_significant_price_changes(threshold=0.05):
    """
    Obtiene cambios de precio significativos (> threshold) desde el histórico.
    Usa window functions para diffs.
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Query con LAG para diff anterior
    query = """
        WITH diffs AS (
            SELECT 
                nombre, precio, fecha, timestamp, wishlist_id,
                LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp) AS prev_precio,
                precio - LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp) AS diff
            FROM precios_cartas
        )
        SELECT nombre, precio, prev_precio, diff, fecha, timestamp, wishlist_id
        FROM diffs 
        WHERE ABS(diff) > ? AND diff IS NOT NULL
        ORDER BY wishlist_id, nombre, fecha DESC
    """
    
    df = pd.read_sql_query(query, conn, params=(threshold,))
    conn.close()
    return df

def analizar_ejemplo(inserted_count=0):
    """
    Analiza ejemplo: stats últimos 30 días y exporta CSV solo si hay cambios/inserts.
    - Condicional: Exporta solo si inserted_count > 0 (nueva data).
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Query últimos 30 días (usa fecha)
    treinta_dias_atras = (datetime.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    query = """
        SELECT nombre, AVG(precio) as media, MIN(precio) as min, MAX(precio) as max,
               COUNT(*) as muestras
        FROM precios_cartas 
        WHERE fecha >= ?
        GROUP BY nombre
        ORDER BY max DESC
    """
    
    df = pd.read_sql_query(query, conn, params=(treinta_dias_atras,))
    conn.close()
    
    if not df.empty:
        print(f"[INFO] Stats últimos 30 días: {len(df)} cartas únicas.")
        print(df.head())
        
        # Export condicional: Solo si hay inserts nuevos
        if inserted_count > 0:
            csv_path = 'historico.csv'
            df.to_csv(csv_path, index=False)
            print(f"[INFO] Exportado CSV a {csv_path} (nuevos cambios detectados).")
        else:
            print("[INFO] Skip export CSV: Sin nuevos inserts.")
    else:
        print("[INFO] Sin data en últimos 30 días.")

# Nota: inicializar_bd() se llama una vez al start, e.g., en main.py