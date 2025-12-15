import requests
import time
from typing import List, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session(token: str):
    """Crea una sesión con retries para CardTrader y Scryfall."""
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({'Authorization': f'Bearer {token}'})
    return session

def preprocess_card_name(slug_name: str) -> str:
    """Convierte slug a nombre legible para Scryfall."""
    words = slug_name.split('-')
    return ' '.join(word.capitalize() for word in words)

def flatten_products(products_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aplana la respuesta de productos (dict o list)."""
    if isinstance(products_data, dict):
        flat = []
        for key, value in products_data.items():
            if isinstance(value, list):
                flat.extend(value)
        return flat
    elif isinstance(products_data, list):
        return products_data
    return []

def sort_key(item: Dict[str, Any]) -> tuple:
    """Clave para ordenar: precio bajo, Foil>NonFoil, NM>SP, ES>EN."""
    price = item['price']
    foil_score = 0 if item['foil'] == 'Yes' else 1
    qual_score = 0 if item['quality'] == 'Near Mint' else 1
    lang_score = 0 if item['language'] == 'ES' else 1
    
    return (price, foil_score, qual_score, lang_score)