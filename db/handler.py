import sqlite3
import pandas as pd
from datetime import datetime

def inicializar_bd(db_file='historico_cartas.db'):
    """
    Inicializa la base de datos (simple, sin extras).
    """
    conn = sqlite3.connect(db_file)
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
    conn.commit()
    conn.close()

def guardar_historial(cartas, db_file='historico_cartas.db', wishlist_id=0):
    """
    Guarda o actualiza el histórico de precios (solo esenciales).
    """
    if not cartas:
        return
    
    inicializar_bd(db_file)
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
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
            cursor.execute('''
                INSERT INTO precios_cartas (nombre, precio, fecha, timestamp, wishlist_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (nombre, precio, fecha, timestamp, wishlist_id))
            guardadas += 1
        else:
            ultimo_precio = resultado[0]
            if abs(precio - ultimo_precio) < 0.01:  # Diferencia menor a 1 céntimo
                print(f"[DEBUG] {nombre}: Precio igual (€{precio} == €{ultimo_precio}). Saltando.")
            else:
                # Precio diferente: registrar nuevo
                print(f"[DEBUG] {nombre}: Precio cambió (€{ultimo_precio} -> €{precio}). Registrando.")
                cursor.execute('''
                    INSERT INTO precios_cartas (nombre, precio, fecha, timestamp, wishlist_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (nombre, precio, fecha, timestamp, wishlist_id))
                guardadas += 1
    
    conn.commit()
    conn.close()
    print(f"¡Guardadas {guardadas} actualizaciones!")

def analizar_ejemplo(db_file='historico_cartas.db'):
    """
    Análisis básico de la DB.
    """
    try:
        conn = sqlite3.connect(db_file)
        df = pd.read_sql_query("SELECT * FROM precios_cartas ORDER BY nombre, timestamp", conn)
        conn.close()
        
        if not df.empty:
            print("\n=== Análisis ===")
            print(f"Registros: {len(df)}")
            print(f"Promedio: €{df['precio'].mean():.2f}")
            
            if len(df) > 1:
                # Ordena por nombre y timestamp para variaciones
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
            print("\nNo datos.")
    except Exception as e:
        print(f"Error análisis: {e}")