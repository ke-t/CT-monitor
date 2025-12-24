import pandas as pd
import sqlite3

def generar_html_stats(db_file='historico_cartas.db', output_file='stats.html'):
    """
    Genera HTML con tabla de stats simple desde la DB (solo precios + wishlist).
    Ajuste: Solo Diff Max en € (actual - Max), sin %.
    """
    conn = sqlite3.connect(db_file)
    df = pd.read_sql_query("""
        SELECT nombre, precio, fecha, timestamp, wishlist_id 
        FROM precios_cartas 
        ORDER BY nombre, timestamp
    """, conn)
    conn.close()
    
    if df.empty:
        print("No datos en DB.")
        return
    
    # Map wishlist_id a nombres (edita este dict con tus IDs reales)
    wishlist_names = {
        2523862: 'Wishlist LOTR', 
        2442303: 'Wishlist Avatar', 
        2404433: 'Wishlist Misc'
    }
    df['wishlist'] = df['wishlist_id'].map(wishlist_names).fillna('Desconocida')
    
    # Stats por nombre
    stats = df.groupby('nombre', as_index=False).agg({
        'precio': ['min', 'max', 'mean', lambda x: x.quantile(0.25)],
        'wishlist': 'first'
    })
    stats.columns = ['Nombre', 'Min.', 'Max.', 'Med.', 'Q1', 'Wishlist']
    
    # € como último precio
    ultimos = df.groupby('nombre')['precio'].last().round(2)
    stats['€'] = stats['Nombre'].map(ultimos)
    
    # AJUSTE: Solo Diff Max en € (actual - Max)
    stats['Diff Max (€)'] = (stats['€'] - stats['Max.']).round(2)
    
    # Reordena columnas
    stats = stats[['Wishlist', 'Nombre', 'Min.', 'Max.', 'Med.', 'Q1', 'Diff Max (€)', '€']]
    
    # Template HTML actualizado (completo)
    html_template = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Estadísticas de Cartas MTG</title>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
</head>
<body>
    <h1>Tabla de Estadísticas de Cartas</h1>
    <div>
        <label>Buscador por Nombre: <input type="text" id="searchName"></label>
        <label>Filtro por Wishlist: 
            <select id="filterWishlist">
                <option value="">Todas</option>
                {wishlist_options}
            </select>
        </label>
    </div>
    <table id="statsTable" class="display">
        <thead>
            <tr>
                <th>Wishlist</th>
                <th>Nombre</th>
                <th>Min.</th>
                <th>Max.</th>
                <th>Med.</th>
                <th>Q1</th>
                <th>Diff Max (€)</th>
                <th>€</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    <script>
        $(document).ready(function() {{
            var table = $('#statsTable').DataTable({{
                "order": [[1, "asc"]],  // Orden inicial por Nombre
                "pageLength": 25,
                "language": {{ "url": "//cdn.datatables.net/plug-ins/1.13.7/i18n/es-ES.json" }}  // Español
            }});

            // Buscador por Nombre (columna 1)
            $('#searchName').on('keyup', function() {{
                table.column(1).search(this.value).draw();
            }});

            // Filtro por Wishlist (columna 0)
            $('#filterWishlist').on('change', function() {{
                var val = this.value;
                if (val) {{
                    table.column(0).search(val).draw();
                }} else {{
                    table.column(0).search('').draw();
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    
    # Opciones de wishlist únicas
    unique_wishlists = sorted(df['wishlist'].unique())
    wishlist_options = ''.join([f'<option value="{w}">{w}</option>' for w in unique_wishlists])
    
    # Filas de tabla
    table_rows = ''
    for _, row in stats.iterrows():
        table_rows += f"""
            <tr>
                <td>{row['Wishlist']}</td>
                <td>{row['Nombre']}</td>
                <td>{row['Min.']:.2f}</td>
                <td>{row['Max.']:.2f}</td>
                <td>{row['Med.']:.2f}</td>
                <td>{row['Q1']:.2f}</td>
                <td>{row['Diff Max (€)']:.2f}</td>
                <td>{row['€']:.2f}</td>
            </tr>
        """
    
    # Reemplaza placeholders
    html_content = html_template.format(wishlist_options=wishlist_options, table_rows=table_rows)
    
    # Escribe archivo
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[INFO] HTML generado: {output_file} con {len(stats)} cartas.")