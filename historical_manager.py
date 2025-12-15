import csv
import os
from datetime import datetime
from typing import List, Dict

HISTORICAL_DIR = 'historical'
OUTPUTS_DIR = 'outputs'

def update_historical(card_name: str, price: float):
    """
    Actualiza el histórico de precios para una carta.
    - Crea registro si no hay para hoy.
    - Si hay para hoy, compara con el último: si cambió, añade nuevo.
    """
    os.makedirs(HISTORICAL_DIR, exist_ok=True)
    csv_file = os.path.join(HISTORICAL_DIR, f"{card_name}.csv")
    
    # Leer registros existentes
    existing: List[Dict[str, str]] = []
    if os.path.exists(csv_file):
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.append({'date': row['date'], 'price': row['price']})
    
    # Ordenar por fecha para asegurar orden
    def parse_date(date_str: str):
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    
    existing.sort(key=lambda x: parse_date(x['date']))
    
    # Fecha de hoy
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_entries = [e for e in existing if e['date'][:10] == today_str]
    
    # Verificar si añadir (sin tolerancia: solo si es diferente)
    add_new = True
    if today_entries:
        last_price = float(today_entries[-1]['price'])
        if last_price == price:  # Comparación exacta
            add_new = False
            print(f"  Histórico: {card_name} - Sin cambio hoy ({price:.2f}€ igual al último).")
    
    if add_new:
        # Añadir nuevo registro
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_entry = {
            'date': now_str,
            'price': f"{price:.2f}"
        }
        existing.append(new_entry)
        print(f"  Histórico: {card_name} - Añadido nuevo ({price:.2f}€).")
    
    # Guardar ordenado
    existing.sort(key=lambda x: parse_date(x['date']))
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['date', 'price']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)

def generate_summary():
    """
    Genera CSV de resumen con estadísticas históricas por carta.
    Columnas: nombre | min | max | Q1 | dif-max | % max | €
    """
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    summary_file = os.path.join(OUTPUTS_DIR, 'historical_summary.csv')
    summary: List[Dict[str, str]] = []
    
    def parse_date(date_str: str):
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    
    for filename in os.listdir(HISTORICAL_DIR):
        if not filename.endswith('.csv'):
            continue
        card_name = filename[:-4]
        csv_file = os.path.join(HISTORICAL_DIR, filename)
        
        rows: List[Dict[str, str]] = []
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        
        if not rows:
            continue
        
        # Ordenar por fecha
        rows.sort(key=lambda x: parse_date(x['date']))
        prices = [float(row['price']) for row in rows]
        current = prices[-1]
        sorted_prices = sorted(prices)
        
        min_p = min(prices)
        max_p = max(prices)
        
        # Q1: percentil 25
        n = len(sorted_prices)
        q1_index = int(n * 0.25)
        q1 = sorted_prices[q1_index] if n > 0 else 0.0
        
        dif_max = current - max_p
        pct_max = (current / max_p * 100) if max_p > 0 else 0.0
        
        summary.append({
            'nombre': card_name,
            'min': f"{min_p:.2f}",
            'max': f"{max_p:.2f}",
            'Q1': f"{q1:.2f}",
            'dif-max': f"{dif_max:.2f}",
            '% max': f"{pct_max:.2f}",
            '€': f"{current:.2f}"
        })
    
    # Ordenar por nombre
    summary.sort(key=lambda x: x['nombre'])
    
    # Escribir CSV
    with open(summary_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['nombre', 'min', 'max', 'Q1', 'dif-max', '% max', '€']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)
    
    print(f"Resumen histórico generado: {summary_file} ({len(summary)} cartas)")