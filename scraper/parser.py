import re
from datetime import datetime

def parsear_cartas(texto):
    """
    Parsea el texto extraído para obtener cartas y precios (simple).
    """
    print(f"[DEBUG] Parseando {len(texto.splitlines())} líneas...")
    lines = [l.strip() for l in texto.split('\n') if l.strip()]
    cartas = []
    fecha = datetime.now().strftime('%Y-%m-%d')
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'^[A-ZÀ-Ú][a-zà-ú]+.*', line) and not line.startswith('€') and 'Indiferente' not in line and line not in ['No', 'Sí'] and len(line) > 5:
            if line[0].isdigit() and ' ' in line:
                parts = line.split(' ', 1)
                nombre = parts[1].strip()
            else:
                nombre = line
            if any(word in nombre.lower() for word in ['sesión', 'zero', 'comprar', 'ahora', 'cerrar', 'cardtrader', 'box', 'tin', 'mazzi', 'bustine', 'dadi', 'tapetes']):
                i += 1
                continue
            j = i + 1
            precio = 0.0
            while j < min(i + 6, len(lines)):
                p_line = lines[j]
                match = re.search(r'€(\d+\.\d{2})', p_line)
                if match:
                    precio = float(match.group(1))
                    break
                j += 1
            if precio > 0:
                cartas.append({'Nombre': nombre, 'Precio': precio, 'Fecha': fecha})
                print(f"[DEBUG] Carta parseada: {nombre} | €{precio}")
            else:
                print(f"[WARNING] Precio cero para {nombre} - saltando.")
            i = j
        i += 1
    print(f"[DEBUG] Total parseadas: {len(cartas)}")
    return cartas