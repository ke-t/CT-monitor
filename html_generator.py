import os
from datetime import datetime
from typing import List, Dict, Any

OUTPUTS_DIR = 'outputs'

def generate_html(results: List[Dict[str, Any]], output_dir: str = OUTPUTS_DIR) -> str:
    """
    Genera un archivo HTML con tabla interactiva de precios.
    
    Args:
        results: Lista de diccionarios con los resultados de precios.
        output_dir: Directorio de salida.
    
    Returns:
        Ruta al archivo HTML generado (siempre el mismo nombre, se sobrescribe).
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if not results:
        print("No hay resultados para generar HTML.")
        return ""
    
    # Recopilar wishlists únicas
    wishlists = sorted(set(r['wishlist'] for r in results))
    options_html = ''.join(f'<option value="{w}">{w}</option>\n' for w in wishlists)
    
    # Construir filas de la tabla
    rows_html = ''.join(
        f'<tr>\n'
        f'<td>{r["wishlist"]}</td>\n'
        f'<td>{r["nombre_carta"]}</td>\n'
        f'<td>{r["calidad"]}{r["idioma"]}{r["foil"]}</td>\n'
        f'<td>{r["precio_euros"]}</td>\n'
        f'</tr>\n'
        for r in results
    )
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_file = os.path.join(output_dir, "precios_actuales.html")
    
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Precios Actuales de Cartas - {timestamp}</title>
    <style>
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; cursor: pointer; }}
        input, select {{ margin: 10px 0; padding: 5px; }}
    </style>
</head>
<body>
    <h1>Precios Actuales de Cartas - {timestamp}</h1>
    <input type="text" id="search" placeholder="Buscar por nombre de carta" onkeyup="filterTable()">
    <select id="wishlistFilter" onchange="filterTable()">
        <option value="">Todas las wishlists</option>
        {options_html}
    </select>
    <table id="pricesTable">
        <thead>
            <tr>
                <th onclick="sortTable(0)">Wishlist</th>
                <th onclick="sortTable(1)">Nombre Carta</th>
                <th>Información</th>
                <th onclick="sortTable(3)">Precio (€)</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    <script>
        let sortDirections = {{}};
        function sortTable(colIndex) {{
            const table = document.getElementById('pricesTable');
            const tbody = table.tBodies[0];
            const rows = Array.from(tbody.rows);
            const dir = sortDirections[colIndex] === 'asc' ? 'desc' : 'asc';
            sortDirections[colIndex] = dir;
            rows.sort((a, b) => {{
                let aText = a.cells[colIndex].textContent.trim();
                let bText = b.cells[colIndex].textContent.trim();
                if (colIndex === 3) {{  // Columna de precio para ordenamiento numérico
                    aText = parseFloat(aText) || 0;
                    bText = parseFloat(bText) || 0;
                    return dir === 'asc' ? aText - bText : bText - aText;
                }} else {{
                    return dir === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText);
                }}
            }});
            rows.forEach(row => tbody.appendChild(row));
        }}
        function filterTable() {{
            const input = document.getElementById('search');
            const filter = input.value.toLowerCase();
            const select = document.getElementById('wishlistFilter');
            const wishlistFilter = select.value;
            const table = document.getElementById('pricesTable');
            const tr = table.getElementsByTagName('tr');
            for (let i = 1; i < tr.length; i++) {{
                const tdName = tr[i].getElementsByTagName('td')[1];
                const tdWl = tr[i].getElementsByTagName('td')[0];
                if (tdName) {{
                    const txtValueName = tdName.textContent || tdName.innerText;
                    const txtValueWl = tdWl.textContent || tdWl.innerText;
                    if (txtValueName.toLowerCase().indexOf(filter) > -1 && 
                        (wishlistFilter === '' || txtValueWl === wishlistFilter)) {{
                        tr[i].style.display = '';
                    }} else {{
                        tr[i].style.display = 'none';
                    }}
                }}
            }}
        }}
    </script>
</body>
</html>"""
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML actualizado en: {html_file} ({len(results)} cartas) - Generado el {timestamp}")
    return html_file