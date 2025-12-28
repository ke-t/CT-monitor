import re
from dotenv import load_dotenv
import os

# Cargar .env para DEBUG_MODE
load_dotenv()

# Flag de debug con modos (consistente con main.py y browser.py)
DEBUG_MODE = os.getenv('DEBUG_MODE', 'off').lower()

def parsear_cartas(texto):
    """
    Parsea el texto crudo de wishlist a lista de dicts {'Nombre': str, 'Precio': float}.
    - Usa regex para extraer bloques de cartas (nombre + precio €X.XX).
    - Filtra inválidos (e.g., no nombres con "Indiferente", precios €0.00 opcional).
    """
    if DEBUG_MODE == 'debug':
        print(f"[DEBUG] Parseando {len(texto.splitlines())} líneas...")
    
    cartas = []
    lines = texto.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # Regex para nombre (línea que empieza con mayúscula, no "Indiferente")
        nombre_match = re.match(r'^([A-Z][^€\n]+?)(?=\nIndiferente|\n€|$)', line)
        if not nombre_match:
            i += 1
            continue
        
        nombre = nombre_match.group(1).strip()
        # Skip si es filler o bad (e.g., "Indiferente", accesorios)
        bad_patterns = [r'^Indiferente$', r'EN\+ESDEENESFRITJPPTZH-CN', r'Near MintSlightly Played', r'SíNo']
        if any(re.search(pat, nombre) for pat in bad_patterns) or len(nombre) < 3:
            i += 1
            continue
        
        # Busca precio en próximas líneas (formato €X.XX)
        precio = 0.0
        j = i + 1
        while j < len(lines) and j < i + 10:  # Máx 10 líneas por carta
            price_line = lines[j].strip()
            price_match = re.search(r'€(\d+\.\d{2})', price_line)
            if price_match:
                try:
                    precio = float(price_match.group(1))
                    break
                except ValueError:
                    pass
            j += 1
        
        if precio > 0:  # Opcional: Skip €0.00 si quieres filtrar
            cartas.append({'Nombre': nombre, 'Precio': precio})
            if DEBUG_MODE == 'debug':
                print(f"[DEBUG] Carta parseada: {nombre} | €{precio:.2f}")
        else:
            if DEBUG_MODE in ['info', 'debug']:
                print(f"[WARNING] Precio €0.00 o inválido para: {nombre}")
        
        i = j  # Salta al siguiente bloque
    
    if DEBUG_MODE in ['info', 'debug']:
        print(f"Total parseadas: {len(cartas)}")
    
    return cartas