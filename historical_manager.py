import os
import sqlite3
from datetime import datetime
from typing import List, Dict

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

def get_all_stats() -> Dict[str, Dict[str, float]]:
    """
    Carga todas las stats históricas por carta de forma eficiente.
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT card_name, price, date FROM prices ORDER BY card_name, date')
    all_data = cursor.fetchall()
    conn.close()
    
    stats = {}
    current_card = None
    prices_list = []
    
    for row in all_data:
        card, price, _ = row  # No usamos date aquí
        if card != current_card:
            if current_card and prices_list:
                sorted_prices = sorted(prices_list)
                n = len(sorted_prices)
                min_p = min(sorted_prices)
                max_p = max(sorted_prices)
                q1 = sorted_prices[int(n * 0.25)] if n > 0 else 0.0
                current = prices_list[-1]
                dif_max = current - max_p
                pct_max = (current / max_p * 100) if max_p > 0 else 0.0
                stats[current_card] = {
                    'min': min_p, 'max': max_p, 'q1': q1,
                    'dif_max': dif_max, 'pct_max': pct_max, 'current': current
                }
            current_card = card
            prices_list = [price]
        else:
            prices_list.append(price)
    
    # Última carta
    if current_card and prices_list:
        sorted_prices = sorted(prices_list)
        n = len(sorted_prices)
        min_p = min(sorted_prices)
        max_p = max(sorted_prices)
        q1 = sorted_prices[int(n * 0.25)] if n > 0 else 0.0
        current = prices_list[-1]
        dif_max = current - max_p
        pct_max = (current / max_p * 100) if max_p > 0 else 0.0
        stats[current_card] = {
            'min': min_p, 'max': max_p, 'q1': q1,
            'dif_max': dif_max, 'pct_max': pct_max, 'current': current
        }
    
    return stats