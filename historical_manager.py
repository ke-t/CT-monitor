import os
import sqlite3
from datetime import datetime
from typing import List, Dict
import csv  # Solo para escribir el summary CSV

DB_PATH = os.path.join('outputs', 'historical.db')

def _init_db():
    """Inicializa la BD si no existe (privada, se llama automáticamente)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_name TEXT NOT NULL,
            date TEXT NOT NULL,
            price REAL NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_card_date ON prices (card_name, date)')
    conn.commit()
    conn.close()

def update_historical(card_name: str, price: float):
    """
    Actualiza el histórico: Inserta si es nuevo o si cambió el precio del día.
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        'SELECT price FROM prices WHERE card_name = ? AND date LIKE ? ORDER BY date DESC LIMIT 1',
        (card_name, f'{today_str}%')
    )
    last_today = cursor.fetchone()
    
    add_new = True
    if last_today and round(last_today[0], 2) == round(price, 2):
        add_new = False
        print(f"  Histórico: {card_name} - Sin cambio hoy ({price:.2f}€ igual al último).")
    
    if add_new:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'INSERT INTO prices (card_name, date, price) VALUES (?, ?, ?)',
            (card_name, now_str, price)
        )
        print(f"  Histórico: {card_name} - Añadido nuevo ({price:.2f}€).")
    
    conn.commit()
    conn.close()

def generate_summary():
    """
    Genera CSV de resumen con stats históricas por carta.
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query para stats por carta
    cursor.execute('''
        SELECT 
            card_name,
            MIN(price) as min_p,
            MAX(price) as max_p
        FROM prices
        GROUP BY card_name
        HAVING COUNT(*) > 0
        ORDER BY card_name
    ''')
    
    rows = cursor.fetchall()
    summary_file = os.path.join('outputs', 'historical_summary.csv')
    
    with open(summary_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['nombre', 'min', 'max', 'Q1', 'dif-max', '% max', '€'])
        
        for row in rows:
            card_name, min_p, max_p = row
            
            # Q1 y current en Python (simple, sin dependencias)
            cursor.execute('SELECT price FROM prices WHERE card_name = ? ORDER BY date', (card_name,))
            prices_list = [r[0] for r in cursor.fetchall()]
            if not prices_list:
                continue
            sorted_prices = sorted(prices_list)
            n = len(sorted_prices)
            q1 = sorted_prices[int(n * 0.25)] if n > 0 else 0.0
            current = prices_list[-1]
            
            dif_max = current - max_p
            pct_max = (current / max_p * 100) if max_p > 0 else 0.0
            
            writer.writerow([
                card_name,
                f"{min_p:.2f}",
                f"{max_p:.2f}",
                f"{q1:.2f}",
                f"{dif_max:.2f}",
                f"{pct_max:.2f}",
                f"{current:.2f}"
            ])
    
    conn.close()
    print(f"Resumen histórico generado: {summary_file} ({len(rows)} cartas)")