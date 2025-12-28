import sqlite3
import pandas as pd
from datetime import datetime
import os

# Importa config para PRICE_DROP_THRESHOLD
from config import PRICE_DROP_THRESHOLD

DB_PATH = 'historico_cartas.db'

def inicializar_bd():
    """
    Inicializa la base de datos SQLite con tabla precios_cartas.
    - Crea tabla SOLO si no existe (evita DROP para preservar históricos).
    - Agrega UNIQUE constraint en (nombre, fecha, timestamp) para evitar duplicados.
    - timestamp como DATETIME (afinidad en SQLite; almacenamos como ISO string).
    - Nota: Si schema cambia, migra manualmente (ver función al final).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Crear tabla SOLO si no existe (preserva datos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS precios_cartas (
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            fecha TEXT NOT NULL,  -- YYYY-MM-DD (para compatibilidad)
            timestamp DATETIME NOT NULL,  -- Full: YYYY-MM-DD HH:MM:SS
            wishlist_id INTEGER NOT NULL,
            UNIQUE(nombre, fecha, timestamp)  -- Evita dups exactos
        )
    """)
    
    # Índices para queries rápidas (solo si no existen)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_fecha ON precios_cartas(wishlist_id, fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nombre_fecha ON precios_cartas(nombre, fecha)")
    
    conn.commit()
    conn.close()
    print(f"[INFO] BD inicializada en {DB_PATH} (tabla preservada si existía).")

def guardar_historial(cartas, wishlist_id):
    """
    Guarda el histórico de precios en batch.
    - Intenta insert siempre (nuevo timestamp), pero UNIQUE evita dups exactos.
    - Solo alerta si cambio >0.01€ (lógica en get_significant_price_changes).
    - Retorna número de filas insertadas.
    """
    if not cartas:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted_count = 0
    inserts = []
    now = datetime.now()
    fecha = now.strftime("%Y-%m-%d")
    timestamp_full = now.strftime("%Y-%m-%d %H:%M:%S")  # Para DATETIME
    
    for carta in cartas:
        nombre = carta['Nombre']
        precio = float(carta['Precio'])
        
        # Check si ya existe EXACTAMENTE el mismo (mismo timestamp)
        cursor.execute("""
            SELECT 1 FROM precios_cartas 
            WHERE nombre = ? AND fecha = ? AND timestamp = ? AND wishlist_id = ?
        """, (nombre, fecha, timestamp_full, wishlist_id))
        if cursor.fetchone():
            continue  # Dup exacto, skip
        
        # Insert nuevo
        inserts.append((nombre, precio, fecha, timestamp_full, wishlist_id))
        inserted_count += 1
    
    if inserts:
        try:
            cursor.executemany("""
                INSERT INTO precios_cartas (nombre, precio, fecha, timestamp, wishlist_id)
                VALUES (?, ?, ?, ?, ?)
            """, inserts)
            conn.commit()
            print(f"[INFO] Insertadas {len(inserts)} nuevas entradas para wishlist {wishlist_id}.")
        except sqlite3.IntegrityError as e:
            print(f"[WARNING] Dup detectado (UNIQUE): {e}. Algunos skips.")
            conn.rollback()
    
    conn.close()
    return inserted_count

def get_significant_price_changes():
    """
    Obtiene bajadas significativas SOLO de la última iteración (fecha más reciente).
    - Condiciones: bajada (actual < previo) Y (actual < Q1 O % drop > PRICE_DROP_THRESHOLD).
    - Usa window functions para diffs y % drop vs. entrada anterior (por nombre/wishlist).
    - Para cada carta: Calcula stats globales (min, max, Q1) sobre todo el histórico.
    - Retorna df con: nombre, wishlist_id, precio (actual), q1_precio, min_precio, max_precio, pct_drop.
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Obtener fecha más reciente
    max_fecha_df = pd.read_sql("SELECT MAX(fecha) AS max_fecha FROM precios_cartas", conn)
    if max_fecha_df.empty or pd.isna(max_fecha_df.iloc[0, 0]):
        conn.close()
        return pd.DataFrame()
    
    max_fecha = max_fecha_df.iloc[0, 0]
    
    # Query para bajadas en fecha reciente (diff <0, con % drop)
    query = """
        WITH diffs AS (
            SELECT 
                nombre, precio, fecha, timestamp, wishlist_id,
                LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp) AS prev_precio,
                (precio - LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp)) AS diff,
                CASE 
                    WHEN LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp) > 0 
                    THEN (LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp) - precio) / 
                         LAG(precio) OVER (PARTITION BY nombre, wishlist_id ORDER BY fecha, timestamp)
                    ELSE 0 
                END AS pct_drop
            FROM precios_cartas
        )
        SELECT nombre, precio, prev_precio, diff, pct_drop, fecha, timestamp, wishlist_id
        FROM diffs 
        WHERE diff < 0 AND diff IS NOT NULL AND fecha = ?
        ORDER BY wishlist_id, nombre, fecha DESC
    """
    
    df_changes = pd.read_sql_query(query, conn, params=(max_fecha,))
    
    if df_changes.empty:
        conn.close()
        return df_changes
    
    # Obtener histórico completo para cartas con bajada
    unique_names = df_changes['nombre'].unique()
    names_placeholder = ','.join(['?' for _ in unique_names])
    full_query = f"""
        SELECT nombre, precio
        FROM precios_cartas 
        WHERE nombre IN ({names_placeholder})
    """
    
    df_full = pd.read_sql_query(full_query, conn, params=tuple(unique_names))
    
    # Calcular stats (Q1 = percentil 25)
    stats = df_full.groupby('nombre').agg({
        'precio': ['min', 'max', lambda x: x.quantile(0.25)]
    }).round(2)
    stats.columns = ['min_precio', 'max_precio', 'q1_precio']
    stats = stats.reset_index()
    
    # Unir stats y filtrar condiciones finales (Q1 o % drop)
    df_changes = df_changes.merge(stats, on='nombre', how='left')
    df_changes['pct_drop'] = df_changes['pct_drop'].round(4)
    df_changes['q1_precio'] = df_changes['q1_precio'].astype(float)
    
    # Filtro: bajada Y ( < Q1 O > threshold % )
    mask = (
        (df_changes['precio'] < df_changes['q1_precio']) | 
        (df_changes['pct_drop'] > PRICE_DROP_THRESHOLD)
    )
    df_final = df_changes[mask][['nombre', 'wishlist_id', 'precio', 'q1_precio', 'min_precio', 'max_precio', 'pct_drop']]
    
    conn.close()
    return df_final

def analizar_ejemplo(inserted_count=0, current_names=None, wishlist_ids=None):
    """
    Analiza últimos 30 días y exporta CSV solo si hay inserts nuevos.
    - Prioridad: Si current_names (lista de nombres actuales), filtra por ellos (histórico solo de elementos actuales).
    - Fallback: Si wishlist_ids, filtra por IDs.
    - Si ninguno, global.
    """
    conn = sqlite3.connect(DB_PATH)
    
    treinta_dias_atras = (datetime.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Query base
    query = """
        SELECT nombre, AVG(precio) as media, MIN(precio) as min, MAX(precio) as max,
               COUNT(*) as muestras
        FROM precios_cartas 
        WHERE fecha >= ?
    """
    params = [treinta_dias_atras]
    
    # Prioridad 1: Filtro por nombres actuales (únicos)
    if current_names:
        unique_current = list(set(current_names))  # Evita dups
        if unique_current:
            names_placeholder = ','.join(['?' for _ in unique_current])
            query += f" AND nombre IN ({names_placeholder})"
            params.extend(unique_current)
            filter_type = "elementos actuales"
        else:
            conn.close()
            return  # Skip si no hay actuales
    # Fallback: Filtro por wishlist
    elif wishlist_ids:
        ids_placeholder = ','.join(['?' for _ in wishlist_ids])
        query += f" AND wishlist_id IN ({ids_placeholder})"
        params.extend(wishlist_ids)
        filter_type = "wishlist"
    else:
        filter_type = "global"
    
    query += """
        GROUP BY nombre
        ORDER BY max DESC
    """
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if not df.empty:
        # Print con filtro
        if current_names:
            print(f"[INFO] Stats últimos 30 días ({filter_type}): {len(df)} cartas únicas.")
        elif wishlist_ids:
            print(f"[INFO] Stats últimos 30 días ({filter_type} {'/'.join(map(str, wishlist_ids))}): {len(df)} cartas únicas.")
        else:
            print(f"[INFO] Stats últimos 30 días ({filter_type}): {len(df)} cartas únicas.")
        print(df.head())
        
        if inserted_count > 0:
            csv_path = 'historico.csv'
            df.to_csv(csv_path, index=False)
            print(f"[INFO] Exportado CSV a {csv_path}.")
        else:
            print("[INFO] Skip export CSV: Sin nuevos inserts.")
    else:
        print(f"[INFO] Sin data en últimos 30 días ({filter_type}).")

# BONUS: Función de migración manual (ejecuta una vez si tienes DB vieja sin 'timestamp')
def migrar_schema_viejo():
    """
    Migra DB antigua (sin timestamp) a nueva (con timestamp).
    - Asume schema viejo: solo nombre, precio, fecha, wishlist_id.
    - Agrega columna timestamp con valor actual para filas existentes.
    - Ejecuta manualmente: from db.handler import migrar_schema_viejo; migrar_schema_viejo()
    """
    backup_path = 'historico_cartas_backup.db'
    if os.path.exists(DB_PATH):
        # Backup primero
        import shutil
        shutil.copy(DB_PATH, backup_path)
        print(f"[INFO] Backup creado: {backup_path}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Si tabla no tiene timestamp, agrégala
    cursor.execute("PRAGMA table_info(precios_cartas)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'timestamp' not in columns:
        # Agregar columna
        cursor.execute("ALTER TABLE precios_cartas ADD COLUMN timestamp DATETIME DEFAULT NULL")
        
        # Llenar con timestamp actual para filas existentes (aprox)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE precios_cartas SET timestamp = ? WHERE timestamp IS NULL", (now_str,))
        
        # Agregar UNIQUE (si no existe; SQLite no soporta bien ADD UNIQUE, recrea tabla si necesario)
        # Para simplicidad: Recrear con datos (solo si <1000 filas aprox)
        df_old = pd.read_sql("SELECT * FROM precios_cartas", conn)
        if len(df_old) < 10000:  # Límite seguro
            cursor.execute("DROP TABLE precios_cartas")
            cursor.execute("""
                CREATE TABLE precios_cartas (
                    nombre TEXT NOT NULL, precio REAL NOT NULL, fecha TEXT NOT NULL,
                    timestamp DATETIME NOT NULL, wishlist_id INTEGER NOT NULL,
                    UNIQUE(nombre, fecha, timestamp)
                )
            """)
            df_old['timestamp'] = now_str  # Asigna mismo para todas (aprox)
            df_old.to_sql('precios_cartas', conn, if_exists='append', index=False)
            print("[INFO] Migración completada: Tabla recreada con timestamp y UNIQUE.")
        else:
            print("[WARNING] DB muy grande para migración auto. Usa backup y migra manual.")
    
    conn.commit()
    conn.close()
    print("[INFO] Migración chequeada: Schema actualizado si era necesario.")