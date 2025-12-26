import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def inicializar_bd(db_file='historico_cartas.db'):
    """
    Inicializa la base de datos (simple, sin extras).
    """
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS precios_cartas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                precio REAL NOT NULL,
                fecha TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                wishlist_id INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_nombre_fecha_timestamp ON precios_cartas (nombre, fecha, timestamp)')
        # Commit automático al salir del with

def guardar_historial(cartas, db_file='historico_cartas.db', wishlist_id=0):
    """
    Guarda o actualiza el histórico de precios (solo esenciales).
    Usa batch insert con executemany para eficiencia.
    """
    if not cartas:
        return
    
    inicializar_bd(db_file)
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        to_insert = []  # Lista para batch: [(nombre, precio, fecha, timestamp, wishlist_id), ...]
        guardadas = 0
        
        for carta in cartas:
            nombre = carta['Nombre']
            precio = carta['Precio']
            fecha = carta['Fecha']
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Consulta el último precio para esta carta en esta fecha
            cursor.execute('''
                SELECT precio FROM precios_cartas 
                WHERE nombre = ? AND fecha = ? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (nombre, fecha))
            resultado = cursor.fetchone()
            
            if resultado is None:
                # No hay histórico: registrar
                print(f"[DEBUG] Nueva carta {nombre}: Registrando €{precio}")
                to_insert.append((nombre, precio, fecha, timestamp, wishlist_id))
                guardadas += 1
            else:
                ultimo_precio = resultado[0]
                if abs(precio - ultimo_precio) < 0.01:  # Diferencia menor a 1 céntimo
                    print(f"[DEBUG] {nombre}: Precio igual (€{precio} == €{ultimo_precio}). Saltando.")
                else:
                    # Precio diferente: registrar nuevo
                    print(f"[DEBUG] {nombre}: Precio cambió (€{ultimo_precio} -> €{precio}). Registrando.")
                    to_insert.append((nombre, precio, fecha, timestamp, wishlist_id))
                    guardadas += 1
        
        # Batch insert si hay algo
        if to_insert:
            cursor.executemany('''
                INSERT INTO precios_cartas (nombre, precio, fecha, timestamp, wishlist_id)
                VALUES (?, ?, ?, ?, ?)
            ''', to_insert)
    
    print(f"¡Guardadas {guardadas} actualizaciones!")

def get_significant_price_changes(db_file='historico_cartas.db', threshold=0.05):
    """
    Nueva función para enhancement: Obtiene cartas con cambios de precio > threshold (€ absolutos)
    respecto al precio anterior. Útil para alertas condicionales en Telegram.
    
    Returns: DataFrame con columnas ['nombre', 'precio_actual', 'precio_anterior', 'diff_euros', 'wishlist_id']
    Si no hay cambios, DF vacío.
    """
    with sqlite3.connect(db_file) as conn:
        # Query completa para calcular diffs con window function (SQLite soporta LAG)
        query = '''
        WITH precios_ordenados AS (
            SELECT nombre, precio, timestamp, wishlist_id,
                   LAG(precio) OVER (PARTITION BY nombre ORDER BY timestamp) AS precio_anterior
            FROM precios_cartas
            ORDER BY nombre, timestamp
        )
        SELECT nombre, precio AS precio_actual, precio_anterior, 
               ABS(precio - precio_anterior) AS diff_euros, wishlist_id
        FROM precios_ordenados
        WHERE precio_anterior IS NOT NULL AND ABS(precio - precio_anterior) > ?
        ORDER BY diff_euros DESC
        '''
        df = pd.read_sql_query(query, conn, params=(threshold,))
    
    if not df.empty:
        print(f"[DEBUG] {len(df)} cambios significativos (>€{threshold}) detectados.")
    return df

def analizar_ejemplo(db_file='historico_cartas.db'):
    """
    Análisis básico de la DB, filtrado a últimos 30 días para relevancia.
    """
    try:
        with sqlite3.connect(db_file) as conn:
            # Filtrar últimos 30 días en query para eficiencia
            fecha_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            df = pd.read_sql_query(
                "SELECT * FROM precios_cartas WHERE timestamp >= ? ORDER BY nombre, timestamp", 
                conn, params=(fecha_limite,)
            )
        
        if not df.empty:
            print("\n=== Análisis (últimos 30 días) ===")
            print(f"Registros: {len(df)}")
            print(f"Promedio: €{df['precio'].mean():.2f}")
            
            if len(df) > 1:
                # Asegurar orden para variaciones
                df_sorted = df.sort_values(['nombre', 'timestamp'])
                df_sorted['variacion'] = df_sorted.groupby('nombre')['precio'].pct_change()
                print("\nCartas con mayor subida (%):")
                subidas = df_sorted[df_sorted['variacion'] > 0].nlargest(5, 'variacion')[['nombre', 'precio', 'variacion']]
                if not subidas.empty:
                    print(subidas.to_string(index=False))
                else:
                    print("Sin subidas detectadas.")
            
            # Último precio por carta (basado en max timestamp)
            ultimo_precio = df.loc[df.groupby('nombre')['timestamp'].idxmax()][['nombre', 'precio']].sort_values('precio', ascending=False).head(10)
            print("\nTop 10 (precios más altos actuales):")
            print(ultimo_precio.to_string(index=False))
            
            df.to_csv('historico.csv', index=False)
            print("\nDatos exportados a 'historico.csv'.")
        else:
            print("\nNo datos en últimos 30 días.")
    except Exception as e:
        print(f"Error análisis: {e}")