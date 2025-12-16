import os
import re  # ← Nuevo: Para slugificación robusta
import historical_manager
from datetime import datetime
from typing import List, Dict, Any

OUTPUTS_DIR = 'outputs'

def generate_html(results: List[Dict[str, Any]], output_dir: str = OUTPUTS_DIR) -> str:
    """
    Genera un archivo HTML con tabla interactiva de precios, incluyendo stats históricas.
    El nombre de la carta es un enlace a CardTrader.
    
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
    
    # Cargar stats históricas para todas las cartas
    all_stats = historical_manager.get_all_stats()
    
    # Recopilar wishlists únicas
    wishlists = sorted(set(r['wishlist'] for r in results))
    options_html = ''.join(f'<option value="{w}">{w}</option>\n' for w in wishlists)
    
    # Función helper para generar set_slug (mejorada con re)
    def get_set_slug(expansion_name: str) -> str:
        slug = expansion_name.lower()
        # Remove common prefixes
        if slug.startswith('universes beyond: '):
            slug = slug[17:]  # len('universes beyond: ')
        # Normalize colons and dashes with spaces
        slug = re.sub(r'\s*:\s*', '-', slug)
        slug = re.sub(r'\s*-\s*', '-', slug)
        # Replace remaining spaces with dashes
        slug = slug.replace(' ', '-')
        # Remove other non-alphanumeric chars except -
        slug = re.sub(r'[^\w\-]', '', slug)
        # Collapse multiple dashes
        slug = re.sub(r'-+', '-', slug)
        # Strip leading/trailing dashes
        slug = slug.strip('-')
        return slug
    
    # Construir filas de la tabla con stats y enlace para nombre
    rows_html = ''
    for r in results:
        card_name = r['nombre_carta']
        card_stats = all_stats.get(card_name, {
            'min': 0.0, 'max': 0.0, 'q1': 0.0, 'dif_max': 0.0, 'pct_max': 0.0
        })
        
        # Generar enlace a CardTrader (sin /en/, slug corregido)
        set_slug = get_set_slug(r['expansion'])
        card_link = f'<a href="https://www.cardtrader.com/cards/{card_name}-{set_slug}" target="_blank">{card_name}</a>'
        
        rows_html += (
            f'<tr>\n'
            f'<td>{r["wishlist"]}</td>\n'
            f'<td>{card_link}</td>\n'
            f'<td>{r["calidad"]}{r["idioma"]}{r["foil"]}</td>\n'
            f'<td>{card_stats["min"]:.2f}</td>\n'
            f'<td>{card_stats["max"]:.2f}</td>\n'
            f'<td>{card_stats["q1"]:.2f}</td>\n'
            f'<td>{card_stats["dif_max"]:.2f}</td>\n'
            f'<td>{card_stats["pct_max"]:.1f}%</td>\n'
            f'<td>{r["precio_euros"]}</td>\n'
            f'</tr>\n'
        )
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_file = os.path.join(output_dir, "precios_actuales.html")
    
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Precios Actuales de Cartas con Histórico - {timestamp}</title>
    <style>
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; cursor: pointer; }}
        input, select {{ margin: 10px 0; padding: 5px; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>Precios Actuales de Cartas con Histórico - {timestamp}</h1>
    <p><em>Los nombres de las cartas son enlaces a su página en CardTrader.</em></p>
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
                <th onclick="sortTable(3)">Min (€)</th>
                <th onclick="sortTable(4)">Max (€)</th>
                <th onclick="sortTable(5)">Q1 (€)</th>
                <th onclick="sortTable(6)">Dif-Max (€)</th>
                <th onclick="sortTable(7)">% Max</th>
                <th onclick="sortTable(8)">Precio (€)</th>
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
                let aNum = parseFloat(aText) || 0;
                let bNum = parseFloat(bText) || 0;
                let isNumeric = false;
                if (colIndex >= 3 && colIndex <= 6) {{
                    // Min, Max, Q1, Dif-Max: numérico directo
                    isNumeric = true;
                }} else if (colIndex === 7) {{
                    // % Max: remover %
                    aNum = parseFloat(aText.replace('%', '')) || 0;
                    bNum = parseFloat(bText.replace('%', '')) || 0;
                    isNumeric = true;
                }} else if (colIndex === 8) {{
                    // Precio: numérico
                    isNumeric = true;
                }}
                if (isNumeric) {{
                    return dir === 'asc' ? aNum - bNum : bNum - aNum;
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