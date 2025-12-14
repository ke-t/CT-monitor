import requests
import csv
import json
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
import os
import statistics  # Para mediana
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sqlite3  # Built-in para DB

# Intento importar tqdm para barra de progreso (opcional)
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("Nota: tqdm no está instalado. Instálalo con 'pip install tqdm' para barra de progreso.")

# Intento importar pandas para HTML y export (opcional)
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Nota: pandas no está instalado. Instálalo con 'pip install pandas' para exportar a HTML/CSV.")

# Directorios base para organización (se crean automáticamente)
DATA_DIR = 'data'
OUTPUTS_DIR = 'outputs'
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
HISTORICAL_FILE = os.path.join(DATA_DIR, 'precios_historicos.db')

DEFAULT_CONFIG = {
    "keep_days": 365,
    "max_workers": 3
}

# Cargar o crear config (con creación de directorio)
def load_config():
    os.makedirs(DATA_DIR, exist_ok=True)  # Asegura que data/ existe
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    else:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"Config creado: {CONFIG_FILE} (valores por defecto). Edítalo para personalizar.")
        return DEFAULT_CONFIG

CONFIG = load_config()
KEEP_DAYS = CONFIG.get("keep_days", 365)
MAX_WORKERS = CONFIG.get("max_workers", 3)

# Función para inicializar DB (una vez)
def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)  # Redundante pero seguro
    conn = sqlite3.connect(HISTORICAL_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS precios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_slug TEXT NOT NULL,
            fecha TEXT NOT NULL,  -- ISO string
            precio REAL NOT NULL
        )
    ''')
    # Índice para queries rápidas
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_slug_fecha ON precios (card_slug, fecha)')
    conn.commit()
    conn.close()

# Función para limpiar histórico viejo (SQL)
def prune_historical(keep_days: int = KEEP_DAYS):
    cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec='seconds')
    conn = sqlite3.connect(HISTORICAL_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM precios WHERE fecha < ?", (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"Limpieza: Borradas {deleted} entradas viejas")
    return deleted

# Función para exportar histórico a CSV (nueva, ahora en outputs/)
def export_historical(csv_file: str = 'historico_completo.csv'):
    if not PANDAS_AVAILABLE:
        print("Pandas no disponible: No se puede exportar histórico.")
        return
    if not os.path.exists(HISTORICAL_FILE):
        print("No hay DB de histórico para exportar.")
        return
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    full_csv_path = os.path.join(OUTPUTS_DIR, csv_file)
    conn = sqlite3.connect(HISTORICAL_FILE)
    df = pd.read_sql_query("SELECT * FROM precios ORDER BY card_slug, fecha", conn)
    df.to_csv(full_csv_path, index=False, encoding='utf-8')
    conn.close()
    print(f"Histórico exportado a: {full_csv_path} ({len(df)} entradas)")

# Función opcional: Migrar JSON viejo a DB (ejecuta una vez)
def migrate_from_json(json_file: str = 'precios_historicos.json'):
    if not os.path.exists(json_file):
        print(f"No hay {json_file} para migrar.")
        return
    historical = json.load(open(json_file, 'r', encoding='utf-8'))
    init_db()
    conn = sqlite3.connect(HISTORICAL_FILE)
    cursor = conn.cursor()
    inserted = 0
    for card_slug, entries in historical.items():
        for entry in entries:
            cursor.execute("INSERT INTO precios (card_slug, fecha, precio) VALUES (?, ?, ?)",
                           (card_slug, entry['fecha'], entry['precio']))
            inserted += 1
    conn.commit()
    conn.close()
    print(f"Migración: Insertadas {inserted} entradas de {json_file}")
    # Borra JSON viejo opcional
    # os.remove(json_file)

# Función para configurar sesión con retries y delays adaptativos
def create_session(token: str):
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  # Espera base 1s, luego 2s, 4s...
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({'Authorization': f'Bearer {token}'})
    return session

# Función para preprocesar el nombre de la carta (slug a nombre legible)
def preprocess_card_name(slug_name: str) -> str:
    words = slug_name.split('-')
    return ' '.join(word.capitalize() for word in words)

# Función para obtener clave de ordenamiento para preferencias
def sort_key(item: Dict[str, Any]) -> tuple:
    price = item['price']
    qual_score = 0 if item['quality'] == 'Near Mint' else 1  # Prefer NM (0) > SP (1)
    lang_score = 0 if item['language'] == 'ES' else 1  # Prefer ES (0) > EN (1)
    foil_score = 0 if item['foil'] == 'Yes' else 1  # Prefer Foil (0) > No (1)
    return (price, qual_score, lang_score, foil_score)

# Función para aplanar la respuesta de productos (dict de blueprint_id a lista)
def flatten_products(products_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(products_data, dict):
        flat = []
        for key, value in products_data.items():
            if isinstance(value, list):
                flat.extend(value)
        return flat
    elif isinstance(products_data, list):
        return products_data
    return []

# Función para obtener todas las impresiones físicas de una carta usando Scryfall - FIX: Filtro digital corregido
def get_card_printings(card_slug: str, session: requests.Session) -> List[Dict[str, Any]]:
    card_name = preprocess_card_name(card_slug)
    
    # Búsqueda fuzzy para encontrar la carta
    search_url = f"https://api.scryfall.com/cards/named?fuzzy={card_name.replace(' ', '+')}"
    resp = session.get(search_url)
    if resp.status_code != 200:
        return []
    card_data = resp.json()
    if card_data['object'] == 'error':
        return []
    
    # Obtener todas las impresiones usando prints_search_uri
    printings_search_url = card_data['prints_search_uri']
    
    all_printings = []
    next_page = printings_search_url
    
    while next_page:
        try:
            resp = session.get(next_page)
            if resp.status_code == 429:
                time.sleep(5)  # Backoff manual para 429 en Scryfall
                resp = session.get(next_page)  # Retry una vez
            if resp.status_code != 200:
                return []
        except Exception:
            return []  # Fail safe
        printings_data = resp.json()
        
        # Filtrar solo impresiones físicas (no digitales) - FIX: Default False para incluir físicas
        physical_printings = [p for p in printings_data['data'] if not p.get('digital', False)]
        all_printings.extend(physical_printings)
        
        # Paginación
        next_page = printings_data.get('next_page')
        if next_page:
            time.sleep(0.3)  # Delay conservador para Scryfall
    
    return all_printings

# Función para INSERT con retry (mejorada: múltiples por día si varía, siempre para día nuevo)
def safe_insert_historical(card_slug: str, precio: float, max_retries: int = 3):
    today_str = date.today().isoformat()
    now_full = datetime.now().isoformat(timespec='seconds')
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(HISTORICAL_FILE)
            cursor = conn.cursor()
            
            # Verificar si ya hay entradas hoy y el último precio
            cursor.execute("""
                SELECT precio FROM precios 
                WHERE card_slug = ? AND substr(fecha, 1, 10) = ? 
                ORDER BY fecha DESC LIMIT 1
            """, (card_slug, today_str))
            last_today_row = cursor.fetchone()
            
            inserted = False
            if last_today_row:
                last_price = last_today_row[0]
                if precio != last_price:  # Diferente: insertar nuevo registro
                    cursor.execute("INSERT INTO precios (card_slug, fecha, precio) VALUES (?, ?, ?)",
                                   (card_slug, now_full, precio))
                    inserted = True
                    print(f"  Insertado nuevo registro para {card_slug}: {precio:.2f}€ (precio diferente dentro del día)")
                else:
                    print(f"  No insertado para {card_slug}: precio igual al último del día ({precio:.2f}€)")
            else:
                # Primer del día: insertar siempre
                cursor.execute("INSERT INTO precios (card_slug, fecha, precio) VALUES (?, ?, ?)",
                               (card_slug, now_full, precio))
                inserted = True
                print(f'  Insertado siempre para {card_slug}: {precio:.2f}€ ("insertado ... (día nuevo)")')
            
            conn.commit()
            conn.close()
            return True
                
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Backoff exponencial
                continue
            else:
                print(f"Error persistente en DB para {card_slug}: {e}")
                return False
        except Exception as e:
            print(f"Error inesperado en DB para {card_slug}: {e}")
            return False
    return False

# Función para procesar una sola carta (para multihilo) - CON CACHE
def process_single_card(item: Dict[str, Any], session: requests.Session, exp_map: Dict[str, Any], 
                        hist_lock: Lock, suggestions_lock: Lock, suggestions: List[str],
                        global_cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Procesa una sola carta. Retorna dict de resultado o None si falla. Usa cache global para evitar reprocesos."""
    card_slug = item.get('meta_name')
    if not card_slug:
        return None
    
    # CACHE: Check si ya procesado en esta run
    if card_slug in global_cache:
        print(f"\nProcesando: {card_slug} (usando cache de wishlist anterior)")
        return global_cache[card_slug]
    
    print(f"\nProcesando: {card_slug} (nuevo)")
    
    expansion_code = item.get('expansion_code')
    collector_num = item.get('collector_number')
    
    # Mejora: Check más estricto para specific_printing
    has_valid_collector = collector_num is not None and str(collector_num).strip() != ''
    specific_printing = expansion_code is not None and has_valid_collector
    
    # Debug print si specific
    if specific_printing:
        print(f"  Debug - Específica: set={expansion_code}, num={collector_num} (str='{str(collector_num)}')")
    else:
        print(f"  Debug - Genérica (no specific: set={expansion_code}, num={collector_num})")
    
    all_printings = get_card_printings(card_slug, session)
    if not all_printings:
        print(f"  No printings encontradas en Scryfall para {card_slug}")
        return None
    
    printings_to_process = []
    if specific_printing:
        expansion_code_lower = expansion_code.lower()
        target_printing = None
        for printing in all_printings:
            if (printing['set'].lower() == expansion_code_lower and
                str(printing['collector_number']) == str(collector_num)):
                target_printing = printing
                break
        if target_printing:
            printings_to_process = [target_printing]
            print(f"  Encontrada impresión específica: {target_printing['set']} #{target_printing['collector_number']}")
        else:
            print(f"  No se encontró la impresión específica en Scryfall para {expansion_code_lower} #{collector_num}")
            print(f"  Fallback: Procesando todas las printings ({len(all_printings)} disponibles)")
            printings_to_process = all_printings  # Fallback clave
    else:
        printings_to_process = all_printings
        print(f"  Procesando todas las printings ({len(all_printings)} disponibles)")
    
    if not printings_to_process:
        print(f"  Sin printings para procesar - skip")
        return None
    
    valid_products = []
    seen_products = set()  # Para deduplicar productos por ID
    item_coll_num = collector_num if has_valid_collector else None
    
    for printing in printings_to_process:
        set_code = printing['set'].lower()
        expansion = exp_map.get(set_code)
        if not expansion:
            print(f"  Skip printing {set_code}: No en exp_map de CardTrader")
            continue
        
        exp_id = expansion['id']
        time.sleep(0.3)  # Delay conservador para no sobrecargar (por expansión)
        # Obtener blueprints para esta expansión
        blueprints_url = f"https://api.cardtrader.com/api/v2/blueprints/export?expansion_id={exp_id}"
        blueprints_resp = session.get(blueprints_url)
        if blueprints_resp.status_code != 200:
            print(f"  Error blueprints {set_code}: {blueprints_resp.status_code}")
            continue
        blueprints = blueprints_resp.json()
        
        # Encontrar blueprint matching scryfall_id o name (+ collector_number si aplica)
        scryfall_id = printing['id']
        print_name = printing['name']
        printing_coll_num = printing['collector_number']
        blueprint = None
        for b in blueprints:
            if b.get('scryfall_id') == scryfall_id:
                blueprint = b
                break
            if b.get('name', '') == print_name:
                if item_coll_num is None or str(b.get('collector_number', '')) == str(printing_coll_num):
                    blueprint = b
                    break
        
        if not blueprint:
            print(f"  No blueprint encontrado para {print_name} en {set_code}")
            continue
        blueprint_id = blueprint['id']
        
        # Consultar productos para las 4 combinaciones (language + foil)
        for lang in ['es', 'en']:
            for is_foil in [False, True]:
                time.sleep(0.1)  # Delay entre consultas de productos
                params = {
                    'blueprint_id': blueprint_id,
                    'language': lang,
                    'foil': str(is_foil).lower()
                }
                products_resp = session.get("https://api.cardtrader.com/api/v2/marketplace/products", params=params)
                if products_resp.status_code != 200:
                    print(f"  Error productos {lang}/{is_foil}: {products_resp.status_code}")
                    continue
                products_data = products_resp.json()
                products = flatten_products(products_data)
                
                for prod in products:
                    prod_id = prod['id']
                    if prod_id in seen_products:
                        continue  # Deduplicar
                    seen_products.add(prod_id)
                    
                    user = prod.get('user', {})
                    if not user.get('can_sell_via_hub', False):
                        continue  # Solo ZERO
                    
                    props = prod.get('properties_hash', {})
                    cond = props.get('condition')
                    if cond not in ['Near Mint', 'Slightly Played']:
                        continue
                    
                    price_data = prod['price']
                    if price_data['currency'] != 'EUR':
                        continue
                    price = price_data['cents'] / 100.0
                    
                    valid_products.append({
                        'expansion': expansion['name'],
                        'codigo': expansion['code'],
                        'language': 'ES' if lang == 'es' else 'EN',
                        'quality': cond,
                        'foil': 'Yes' if is_foil else 'No',
                        'price': price
                    })
    
    print(f"  Total productos válidos encontrados: {len(valid_products)}")
    # Encontrar la mejor (más barata, con preferencias)
    if valid_products:
        best = min(valid_products, key=sort_key)
        current_price = best['price']
        min_price_count = sum(1 for p in valid_products if p['price'] == current_price)
        
        # Estadísticas del histórico (query SQL) - FIX: Maneja len==1
        hist_prices = []
        with hist_lock:
            conn = sqlite3.connect(HISTORICAL_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT precio FROM precios WHERE card_slug = ? ORDER BY fecha", (card_slug,))
            hist_prices = [row[0] for row in cursor.fetchall()]
            conn.close()
        
        if hist_prices:
            max_hist = max(hist_prices)
            min_hist = min(hist_prices)
            median_hist = statistics.median(hist_prices)
            if len(hist_prices) >= 2:
                q1_hist = statistics.quantiles(hist_prices, n=4)[0]
            else:  # len == 1
                q1_hist = hist_prices[0]  # Usa el único valor como Q1 (evita error)
        else:
            max_hist = min_hist = median_hist = q1_hist = None
        
        # Indicador de color
        color_indicator = 'Sin histórico'
        if hist_prices:
            if current_price <= q1_hist:
                color_indicator = '🟢 Barato (cerca del Q1)'
            elif current_price <= median_hist:
                color_indicator = '🟡 Medio (cerca de la mediana)'
            else:
                color_indicator = '🔴 Caro (cerca del máximo)'
        
        result = {
            'nombre_carta': card_slug,
            'expansion': best['expansion'],
            'codigo': best['codigo'],
            'idioma': best['language'],
            'calidad': best['quality'],
            'foil': best['foil'],
            'precio_euros': f"{current_price:.2f}",
            'copias_min_precio': min_price_count,
            'max_historico': f"{max_hist:.2f}" if max_hist else 'N/A',
            'mediana_historico': f"{median_hist:.2f}" if median_hist else 'N/A',
            'q1_historico': f"{q1_hist:.2f}" if q1_hist else 'N/A',
            'min_historico': f"{min_hist:.2f}" if min_hist else 'N/A',
            'indicador_color': color_indicator
        }
        
        print(f"Mejor: {best['expansion']} - {best['language']} - {best['quality']} - {best['foil']} - {current_price:.2f}€ ({min_price_count} copias disponibles)")
        
        if hist_prices:
            print(f"Histórico: Max {max_hist:.2f}€ | Mediana {median_hist:.2f}€ | Q1 {q1_hist:.2f}€ | Min {min_hist:.2f}€ | {color_indicator}")
        else:
            print(f"Histórico: Sin datos | {color_indicator}")
        
        # Actualizar histórico (INSERT con retry, thread-safe: múltiples si varía dentro del día)
        if safe_insert_historical(card_slug, current_price):
            print(f"  Histórico manejado para {card_slug} (múltiples registros por día si varía).")
        else:
            print(f"  ⚠️ Falló manejo de histórico para {card_slug}.")
        
        # Análisis para sugerencia (mejorado: Q1 + % descuento vs mediana)
        if len(hist_prices) > 1:
            if current_price <= q1_hist:
                suggestion = f"SUGERENCIA: ¡Compra {card_slug}! Precio actual ({current_price:.2f}€) está en Q1 del histórico ({q1_hist:.2f}€)."
                print(f"  {suggestion}")
                with suggestions_lock:
                    suggestions.append(suggestion)
            if median_hist and current_price < 0.8 * median_hist:  # >20% descuento
                discount_pct = ((median_hist - current_price) / median_hist) * 100
                suggestion = f"SUGERENCIA: {card_slug} con {discount_pct:.1f}% descuento vs mediana ({median_hist:.2f}€). ¡Oportunidad!"
                print(f"  {suggestion}")
                with suggestions_lock:
                    suggestions.append(suggestion)
        else:
            print(f"  Histórico inicial para {card_slug}.")
        
        # CACHE: Guardar resultado en cache global
        global_cache[card_slug] = result
        print(f"  Cacheado para futuras wishlists.")
        
        return result
    else:
        print(f"  No se encontró ninguna opción válida para {card_slug}.")
        # CACHE: Incluso si None, cachea para evitar reintentos
        global_cache[card_slug] = None
        return None

# Función para enviar mensaje a Telegram
def send_telegram_message(token: str, chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'  # Para formato bonito (negritas, etc.)
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Mensaje enviado a Telegram exitosamente.")
        else:
            print(f"❌ Error enviando a Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Excepción al enviar a Telegram: {e}")

# Función principal
def main():
    # Crear directorios base al inicio
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    
    # Opcional: Migrar JSON viejo (comenta si no necesitas)
    # migrate_from_json()
    
    # 1. Leer token del archivo 'tk'
    try:
        with open('tk', 'r') as f:
            token = f.read().strip()
    except FileNotFoundError:
        print("Error: Archivo 'tk' no encontrado.")
        return
    
    # Inicializar DB y limpiar
    init_db()
    prune_historical()
    
    # Crear sesión con retries
    session = create_session(token)
    base_url = 'https://api.cardtrader.com/api/v2'
    
    # Obtener todas las expansiones de CardTrader (una sola vez)
    expansions_resp = session.get(f'{base_url}/expansions')
    if expansions_resp.status_code != 200:
        print("Error al obtener expansiones de CardTrader.")
        return
    expansions = expansions_resp.json()
    # Diccionario para mapear código de set a expansión
    exp_map = {e['code'].lower(): e for e in expansions if e['game_id'] == 1}  # Solo MTG (game_id=1)
    print(f"Expansiones cargadas: {len(exp_map)}")
    
    # Locks para thread-safety
    hist_lock = Lock()
    suggestions_lock = Lock()
    suggestions = []  # Lista thread-safe con lock
    
    # CACHE: Cache global para resultados únicos por card_slug en esta run
    global_cache = {}
    
    # 2. Solicitar el ID de la wishlist
    wishlist_id = input("Introduce el ID de la wishlist de CardTrader (o presiona Enter para usar archivo 'wishlist'): ").strip()
    
    # Si vacío, leer del archivo 'wishlist'
    wishlist_ids = []
    if not wishlist_id:
        wishlist_file = 'wishlist'
        if os.path.exists(wishlist_file):
            with open(wishlist_file, 'r') as f:
                for line in f:
                    id_candidate = line.strip()
                    if id_candidate and not id_candidate.startswith('#'):  # Ignora líneas vacías y comentarios
                        wishlist_ids.append(id_candidate)
            if not wishlist_ids:
                print("Archivo 'wishlist' vacío o sin IDs válidos.")
                return
            print(f"Procesando {len(wishlist_ids)} IDs del archivo 'wishlist': {', '.join(wishlist_ids)}")
        else:
            print("Archivo 'wishlist' no encontrado. Crea uno con IDs (uno por línea).")
            return
    else:
        wishlist_ids = [wishlist_id]
        print(f"Procesando ID manual: {wishlist_id}")
    
    # Loop para procesar cada ID secuencialmente
    all_results = {}  # Acumular todos los resultados únicos
    for current_wishlist_id in wishlist_ids:
        print(f"\n=== Procesando wishlist ID: {current_wishlist_id} ===")
        
        # Obtener la wishlist
        wishlist_resp = session.get(f"{base_url}/wishlists/{current_wishlist_id}")
        if wishlist_resp.status_code != 200:
            print(f"Error al obtener la wishlist {current_wishlist_id} de CardTrader.")
            continue  # Salta a la siguiente, no para todo
        wishlist = wishlist_resp.json()
        wishlist_name = wishlist['name']
        
        # Preparar items únicos (por wishlist, pero usará cache global)
        unique_items = {}
        for item in wishlist['items']:
            card_slug = item.get('meta_name')
            if card_slug and card_slug not in unique_items:
                unique_items[card_slug] = item
        
        items_list = list(unique_items.values())
        print(f"Procesando {len(items_list)} cartas únicas de la wishlist '{wishlist_name}' con {MAX_WORKERS} workers (usando cache global)")
        
        # 3. Procesar con multihilo (por wishlist) - PASAR CACHE
        card_results = {}
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit tasks
            future_to_item = {
                executor.submit(process_single_card, item, session, exp_map, hist_lock, suggestions_lock, suggestions, global_cache): item 
                for item in items_list
            }
            
            # Progreso con tqdm o simple
            if TQDM_AVAILABLE:
                progress_iter = tqdm(as_completed(future_to_item), total=len(items_list), desc="Procesando cartas", unit="carta")
            else:
                progress_iter = as_completed(future_to_item)
                print("Usando loop simple (sin barra de progreso).")
            
            for future in progress_iter:
                item = future_to_item[future]
                try:
                    result = future.result()
                    if result:
                        card_slug = result['nombre_carta']
                        card_results[card_slug] = result
                        all_results[card_slug] = result  # Acumula global único
                except Exception as exc:
                    card_slug = item.get('meta_name', 'unknown')
                    print(f"Error procesando {card_slug}: {exc}")
        
        # Resto del procesamiento por wishlist (CSV, HTML, etc.)
        results = list(card_results.values())
        
        # 4. Crear CSV (con todas las columnas originales)
        if results:
            # Crear directorio para esta wishlist si no existe (ahora en outputs/wishlist/)
            wishlist_subdir = os.path.join(OUTPUTS_DIR, 'wishlist', current_wishlist_id)
            os.makedirs(wishlist_subdir, exist_ok=True)
            
            csv_filename = os.path.join(wishlist_subdir, f"{wishlist_name}_resultados.csv")
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'nombre_carta', 'expansion', 'codigo', 'idioma', 'calidad', 'foil', 'precio_euros',
                    'copias_min_precio', 'max_historico', 'mediana_historico', 'q1_historico',
                    'min_historico', 'indicador_color'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            print(f"\nCSV creado: {csv_filename} (con columnas completas)")
            
            # 5. Crear HTML con estructura específica (nombre / min / max / mediana / Q1 / actual / indicador)
            if PANDAS_AVAILABLE:
                # Seleccionar solo las columnas solicitadas
                df = pd.DataFrame(results)[['nombre_carta', 'min_historico', 'max_historico', 'mediana_historico', 'q1_historico', 'precio_euros', 'indicador_color']]
                html_filename = os.path.join(wishlist_subdir, f"{wishlist_name}_resumen.html")
                html_content = df.to_html(index=False, escape=False, classes='table table-striped table-hover', table_id='resumen-cartas')
                # Agrega estilos básicos para colores
                html_content = f"""
                <html><head><style>
                .table {{ border-collapse: collapse; width: 100%; }}
                .table th, .table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                .table th {{ background-color: #f2f2f2; }}
                td:has-text(🟢) {{ background-color: #d4edda; }}
                td:has-text(🟡) {{ background-color: #fff3cd; }}
                td:has-text(🔴) {{ background-color: #f8d7da; }}
                </style></head><body>{html_content}</body></html>
                """
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"HTML creado: {html_filename} (abre en tu navegador para ver la tabla: nombre / min / max / mediana / Q1 / actual / indicador)")
            else:
                print("Instala pandas para generar el HTML: pip install pandas")
        else:
            print(f"\nNo se encontraron resultados para wishlist {current_wishlist_id}. Revisa los debug prints para más info.")
    
    # Al final de todas las wishlists, chequeo de DB y sugerencias globales
    if os.path.exists(HISTORICAL_FILE):
        file_size_mb = os.path.getsize(HISTORICAL_FILE) / (1024 * 1024)
        print(f"\nTamaño actual del histórico DB: {file_size_mb:.2f} MB")
        if file_size_mb > 500:
            print("⚠️ Histórico grande: Considera aumentar KEEP_DAYS o limpiar manual.")
        
        # Export histórico si hay datos (nuevo)
        export_historical()
    
    # Mostrar sugerencias (acumula de todas las wishlists)
    if suggestions:
        print("\n=== SUGERENCIAS DE COMPRA (GLOBALES) ===")
        for sug in suggestions:
            print(sug)
        
        # Enviar a Telegram
        try:
            with open('telegram_token.txt', 'r') as f:
                tg_token = f.read().strip()
            with open('telegram_chat_id.txt', 'r') as f:
                tg_chat_id = f.read().strip()
            
            # Formatear mensaje para Telegram (con negritas y emojis)
            msg = "<b>🛒 SUGERENCIAS DE COMPRA MTG - " + datetime.now().strftime('%Y-%m-%d %H:%M') + "</b>\n\n"
            for i, sug in enumerate(suggestions, 1):
                msg += f"{i}. {sug}\n\n"
            msg += f"Total: {len(suggestions)} sugerencias. ¡Revisa los CSV/HTML!"
            
            send_telegram_message(tg_token, tg_chat_id, msg)
        except FileNotFoundError:
            print("⚠️ Archivos telegram_token.txt o telegram_chat_id.txt no encontrados. No se envía mensaje.")
        except Exception as e:
            print(f"❌ Error preparando Telegram: {e}")
    else:
        print("\nNo hay sugerencias de compra en este momento (necesita al menos 2 ejecuciones para Q1).")
        
        # Opcional - Enviar mensaje de "sin sugerencias"
        try:
            with open('telegram_token.txt', 'r') as f:
                tg_token = f.read().strip()
            with open('telegram_chat_id.txt', 'r') as f:
                tg_chat_id = f.read().strip()
            send_telegram_message(tg_token, tg_chat_id, "<b>📭 Sin sugerencias de compra hoy.</b>\nEjecuta de nuevo mañana para actualizar histórico.")
        except FileNotFoundError:
            print("⚠️ Archivos telegram no encontrados. Omitiendo mensaje de 'sin sugerencias'.")
    
    print(f"Histórico guardado en: {HISTORICAL_FILE}")
    print(f"Cartas únicas procesadas en total: {len(all_results)}")
    
    # Opcional - Si quieres un CSV/HTML global de todas las wishlists
    if len(wishlist_ids) > 1 and all_results:
        global_subdir = os.path.join(OUTPUTS_DIR, 'global')
        os.makedirs(global_subdir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        global_csv = os.path.join(global_subdir, f"resumen_todas_wishlists_{timestamp}.csv")
        with open(global_csv, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'nombre_carta', 'expansion', 'codigo', 'idioma', 'calidad', 'foil', 'precio_euros',
                'copias_min_precio', 'max_historico', 'mediana_historico', 'q1_historico',
                'min_historico', 'indicador_color'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results.values())
        print(f"\nCSV global creado: {global_csv} (todas las cartas únicas)")
        
        if PANDAS_AVAILABLE:
            df_global = pd.DataFrame(list(all_results.values()))[['nombre_carta', 'min_historico', 'max_historico', 'mediana_historico', 'q1_historico', 'precio_euros', 'indicador_color']]
            global_html = os.path.join(global_subdir, f"resumen_todas_wishlists_{timestamp}.html")
            html_content = df_global.to_html(index=False, escape=False, classes='table table-striped table-hover', table_id='resumen-global')
            html_content = f"""
            <html><head><style>
            .table {{ border-collapse: collapse; width: 100%; }}
            .table th, .table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            .table th {{ background-color: #f2f2f2; }}
            td:has-text(🟢) {{ background-color: #d4edda; }}
            td:has-text(🟡) {{ background-color: #fff3cd; }}
            td:has-text(🔴) {{ background-color: #f8d7da; }}
            </style></head><body>{html_content}</body></html>
            """
            with open(global_html, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"HTML global creado: {global_html}")

if __name__ == "__main__":
    main()