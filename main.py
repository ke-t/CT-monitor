import csv
import os
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("Instala tqdm para barra de progreso: pip install tqdm")

from api_utils import create_session
from card_processor import process_single_card

# Directorios
OUTPUTS_DIR = 'outputs'
MAX_WORKERS = 3  # ← Ajusta: 3-5 para balance velocidad/seguridad

def main():
    load_dotenv()
    
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    
    # Leer token de var de entorno
    token = os.getenv('CARDTRADER_TOKEN')
    if not token:
        print("Error: CARDTRADER_TOKEN no encontrado en .env. Crea el archivo y agrega tu token.")
        return
    
    session = create_session(token)
    base_url = 'https://api.cardtrader.com/api/v2'
    
    # Obtener expansiones (con delay para estabilidad)
    time.sleep(2)  # ← Inicial para "calentar"
    expansions_resp = session.get(f'{base_url}/expansions')
    if expansions_resp.status_code != 200:
        print(f"Error expansiones: {expansions_resp.status_code} - {expansions_resp.text[:100]}")
        return
    expansions = expansions_resp.json()
    exp_map = {e['code'].lower(): e for e in expansions if e['game_id'] == 1}
    print(f"Expansiones: {len(exp_map)}")
    
    # Wishlist ID
    wishlist_id = input("ID de wishlist: ").strip()
    if not wishlist_id:
        print("ID requerido.")
        return
    
    # Obtener wishlist
    wishlist_resp = session.get(f"{base_url}/wishlists/{wishlist_id}")
    if wishlist_resp.status_code != 200:
        print("Error wishlist.")
        return
    wishlist = wishlist_resp.json()
    
    # Items únicos
    unique_items = {}
    for item in wishlist['items']:
        card_slug = item.get('meta_name')
        if card_slug:
            unique_items[card_slug] = item
    
    items_list = list(unique_items.values())
    print(f"Procesando {len(items_list)} cartas con {MAX_WORKERS} workers...")
    
    # Multihilo: Submit tasks
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_item = {
            executor.submit(process_single_card, item, session, exp_map): item 
            for item in items_list
        }
        
        # Progreso
        if TQDM_AVAILABLE:
            progress_iter = tqdm(as_completed(future_to_item), total=len(items_list), desc="Procesando cartas")
        else:
            progress_iter = as_completed(future_to_item)
        
        for future in progress_iter:
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as exc:
                item = future_to_item[future]
                card_slug = item.get('meta_name', 'unknown')
                print(f"Error en {card_slug}: {exc}")
    
    # Output CSV simple
    if results:
        csv_file = os.path.join(OUTPUTS_DIR, f"wishlist_{wishlist_id}_precios_actuales.csv")
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['nombre_carta', 'expansion', 'codigo', 'idioma', 'calidad', 'foil', 'precio_euros']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nPrecios actuales en: {csv_file} ({len(results)} cartas)")
    else:
        print("No resultados.")

if __name__ == "__main__":
    main()