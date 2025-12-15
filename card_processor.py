import time
import requests
from typing import List, Dict, Any
from collections import deque

from api_utils import preprocess_card_name, flatten_products, sort_key

# CONFIGURACIÓN GLOBAL: Edita aquí para tunear delays y límites
CT_WINDOW = 10.0  # Ventana de CardTrader (segundos, fijo por docs)
CT_LIMIT = 200    # Límite de req en CT_WINDOW
CT_MARGIN = 10    # Margen de seguridad: Pausa si > (CT_LIMIT - CT_MARGIN) req

DELAY_BLUEPRINTS = 0.15  # antes de blueprints
DELAY_PRODUCTS = 0.1   	 # entre lang/foil
DELAY_SCRYFALL = 0.1     # Para búsquedas/páginas en Scryfall (conservador)

# Rate limiter para CardTrader
CT_REQUESTS = deque()  # Cola de timestamps

def ct_rate_check():
    """Pausa si cerca del límite de CardTrader."""
    now = time.time()
    while CT_REQUESTS and now - CT_REQUESTS[0] > CT_WINDOW:
        CT_REQUESTS.popleft()
    current_count = len(CT_REQUESTS)
    if current_count >= (CT_LIMIT - CT_MARGIN):
        sleep_time = CT_WINDOW - (now - CT_REQUESTS[0])
        print(f"  Rate limit CT cerca ({current_count}/{CT_LIMIT}): Esperando {sleep_time:.1f}s")
        time.sleep(max(0, sleep_time))
    CT_REQUESTS.append(now)

def get_card_printings(card_slug: str, session: requests.Session) -> List[Dict[str, Any]]:
    """Obtiene todas las impresiones físicas de una carta de Scryfall."""
    card_name = preprocess_card_name(card_slug)
    search_url = f"https://api.scryfall.com/cards/named?fuzzy={card_name.replace(' ', '+')}"
    resp = session.get(search_url)
    time.sleep(DELAY_SCRYFALL)
    if resp.status_code != 200:
        return []
    card_data = resp.json()
    if card_data['object'] == 'error':
        return []
    
    printings_search_url = card_data['prints_search_uri']
    all_printings = []
    next_page = printings_search_url
    
    while next_page:
        resp = session.get(next_page)
        time.sleep(DELAY_SCRYFALL)
        if resp.status_code == 429:
            time.sleep(5)
            resp = session.get(next_page)
        if resp.status_code != 200:
            return []
        printings_data = resp.json()
        physical_printings = [p for p in printings_data['data'] if not p.get('digital', False)]
        all_printings.extend(physical_printings)
        next_page = printings_data.get('next_page')
        if next_page:
            time.sleep(0.3)  # ← Mantiene 0.3s para paginación (pocas páginas)
    
    return all_printings

def process_single_card(item: Dict[str, Any], session: requests.Session, exp_map: Dict[str, Any]):
    """Procesa una carta: busca productos Zero y devuelve la mejor oferta."""
    card_slug = item.get('meta_name')
    if not card_slug:
        return None
    
    print(f"\nProcesando: {card_slug}")
    
    expansion_code = item.get('expansion_code')
    collector_num = item.get('collector_number')
    has_valid_collector = collector_num is not None and str(collector_num).strip() != ''
    specific_printing = expansion_code is not None and has_valid_collector
    
    all_printings = get_card_printings(card_slug, session)
    if not all_printings:
        print(f"  No printings encontradas")
        return None
    
    printings_to_process = all_printings
    if specific_printing:
        expansion_code_lower = expansion_code.lower()
        target_printing = next((p for p in all_printings if p['set'].lower() == expansion_code_lower and str(p['collector_number']) == str(collector_num)), None)
        if target_printing:
            printings_to_process = [target_printing]
            print(f"  Usando impresión específica")
        else:
            print(f"  Fallback a todas las printings")
    
    valid_products = []
    seen_products = set()
    
    for printing in printings_to_process:
        set_code = printing['set'].lower()
        expansion = exp_map.get(set_code)
        if not expansion:
            continue
        
        exp_id = expansion['id']
        ct_rate_check()  # ← Limiter CT
        time.sleep(DELAY_BLUEPRINTS)  # ← Variable reducido
        blueprints_url = f"https://api.cardtrader.com/api/v2/blueprints/export?expansion_id={exp_id}"
        blueprints_resp = session.get(blueprints_url)
        if blueprints_resp.status_code != 200:
            continue
        blueprints = blueprints_resp.json()
        
        scryfall_id = printing['id']
        print_name = printing['name']
        blueprint = next((b for b in blueprints if b.get('scryfall_id') == scryfall_id or b.get('name', '') == print_name), None)
        if not blueprint:
            continue
        blueprint_id = blueprint['id']
        
        for lang in ['es', 'en']:
            for is_foil in [False, True]:
                ct_rate_check()
                time.sleep(DELAY_PRODUCTS)
                params = {'blueprint_id': blueprint_id, 'language': lang, 'foil': str(is_foil).lower()}
                products_resp = session.get("https://api.cardtrader.com/api/v2/marketplace/products", params=params)
                if products_resp.status_code != 200:
                    continue
                products_data = products_resp.json()
                products = flatten_products(products_data)
                
                for prod in products:
                    prod_id = prod['id']
                    if prod_id in seen_products:
                        continue
                    seen_products.add(prod_id)
                    
                    user = prod.get('user', {})
                    if not user.get('can_sell_via_hub', False) or user.get('on_vacation', False):
                        continue
                    
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
                        'price': price,
                        'product_id': prod['id']
                    })
    
    if not valid_products:
        print(f"  No productos válidos (Zero)")
        return None
    
    best = min(valid_products, key=sort_key)
    current_price = best['price']
    foil_icon = '🔶' if best['foil'] == 'Yes' else ''
    flag = '🇪🇸' if best['language'] == 'ES' else '🇺🇸'
    quality_abbr = 'NM' if best['quality'] == 'Near Mint' else 'SP'

    print(f"  Mejor: {card_slug} {flag} {quality_abbr} {foil_icon} - {current_price:.2f}€")
    
    return {
        'nombre_carta': card_slug,
        'expansion': best['expansion'],
        'codigo': best['codigo'],
        'idioma': flag,
        'calidad': quality_abbr,
        'foil': foil_icon,
        'precio_euros': f"{current_price:.2f}"
    }