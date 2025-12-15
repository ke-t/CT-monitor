import csv
import os
import time
import requests
import sys
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
from scheduler import get_wishlist_id, run_scheduler

# Directorios
OUTPUTS_DIR = 'outputs'
MAX_WORKERS = 3  # Ajusta: 3-5 para balance velocidad/seguridad

def process_wishlist(wishlist_id: str, session: requests.Session, base_url: str, exp_map: Dict[str, Any]) -> int:
    """Procesa una wishlist individual y devuelve el número de resultados."""
    print(f"\nObteniendo wishlist {wishlist_id}...")
    
    wishlist_resp = session.get(f"{base_url}/wishlists/{wishlist_id}")
    if wishlist_resp.status_code != 200:
        print(f"Error en wishlist {wishlist_id}: {wishlist_resp.status_code}")
        return 0
    
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
            progress_iter = tqdm(as_completed(future_to_item), total=len(items_list), desc=f"Procesando cartas ({wishlist_id})")
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
    
    # Output CSV para esta wishlist
    if results:
        csv_file = os.path.join(OUTPUTS_DIR, f"wishlist_{wishlist_id}_precios_actuales.csv")
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['nombre_carta', 'expansion', 'codigo', 'idioma', 'calidad', 'foil', 'precio_euros']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"Precios actuales en: {csv_file} ({len(results)} cartas)")
        return len(results)
    else:
        print(f"No resultados para {wishlist_id}.")
        return 0

def processing_func(wishlist_id: str | None = None) -> int:
    """Función principal de procesamiento: Maneja input, sesión, expansiones y wishlists."""
    load_dotenv()
    
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    
    # Leer token de var de entorno con fallback
    token = os.getenv('CARDTRADER_TOKEN')
    if not token:
        token = input("CARDTRADER_TOKEN no encontrado en .env. Ingresa tu token: ").strip()
        if not token:
            print("Error: Token requerido.")
            return 0
    
    session = create_session(token)
    base_url = 'https://api.cardtrader.com/api/v2'
    
    # Obtener expansiones (con delay para estabilidad)
    time.sleep(2)  # Inicial para "calentar"
    expansions_resp = session.get(f'{base_url}/expansions')
    if expansions_resp.status_code != 200:
        print(f"Error expansiones: {expansions_resp.status_code} - {expansions_resp.text[:100]}")
        return 0
    expansions = expansions_resp.json()
    exp_map = {e['code'].lower(): e for e in expansions if e['game_id'] == 1}
    print(f"Expansiones: {len(exp_map)}")
    
    # Input con opción para archivo (bloqueante si None)
    if wishlist_id is None:
        wishlist_id = get_wishlist_id(block=True)
    
    total_processed = 0
    if not wishlist_id:
        # Modo archivo
        file_path = 'wishlists'
        try:
            with open(file_path, 'r') as f:
                wishlist_ids = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        except FileNotFoundError:
            print(f"Error: No se encontró {file_path}. Crea el archivo con IDs de wishlists, uno por línea.")
            return 0
        except Exception as e:
            print(f"Error al leer {file_path}: {e}")
            return 0
        
        if not wishlist_ids:
            print(f"Archivo {file_path} vacío. Agrega IDs de wishlists.")
            return 0
        
        print(f"Procesando {len(wishlist_ids)} wishlists desde {file_path}...")
        for wid in wishlist_ids:
            processed = process_wishlist(wid, session, base_url, exp_map)
            total_processed += processed
            if processed == 0:
                print(f"  Saltando {wid} (sin resultados o error).")
            time.sleep(1)  # Pequeña pausa entre wishlists para estabilidad
    else:
        # Modo single
        total_processed = process_wishlist(wishlist_id, session, base_url, exp_map)
    
    print(f"\n¡Listo! Total de cartas procesadas: {total_processed}")
    return total_processed

if __name__ == "__main__":
    load_dotenv()
    
    # Lee intervalo de .env con fallback
    interval_minutes = int(os.getenv('INTERVAL_MINUTES', 60))
    
    # Para ejecutar solo una vez (modo legacy)
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        processing_func()
    else:
        # Modo scheduler: Usa el intervalo de .env
        run_scheduler(processing_func, interval_minutes=interval_minutes)