# MTG Price Tracker para CardTrader

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Descripción

Este script es una herramienta automatizada para monitorear los precios de cartas de **Magic: The Gathering (MTG)** en la plataforma **CardTrader**. Utiliza la API de CardTrader para obtener precios actuales de wishlists, integra **Scryfall API** para identificar impresiones físicas de cartas, y mantiene un histórico de precios en una base de datos SQLite local. Genera reportes en CSV y HTML con análisis estadísticos (máximo, mediana, Q1, mínimo) y envía sugerencias de compra por **Telegram** cuando detecta oportunidades basadas en el histórico.

**Características clave:**
- Procesamiento multihilo para wishlists múltiples.
- Detección de impresiones específicas o genéricas (fallback automático).
- Preferencias: Prioriza Near Mint, español, foil.
- Limpieza automática de datos históricos antiguos.
- Sugerencias inteligentes: Compra si precio ≤ Q1 o >20% descuento vs mediana.
- Exportación a CSV/HTML con indicadores de color (🟢 Barato, 🟡 Medio, 🔴 Caro).

Ideal para coleccionistas que quieren rastrear evoluciones de precios y alertas de gangas.

## Requisitos

- **Python 3.8+** (probado en 3.12).
- Bibliotecas estándar: `requests`, `csv`, `json`, `sqlite3`, `statistics`, `concurrent.futures`, `threading`, `os`, `datetime`.
- Opcionales (mejoran la experiencia):
  - `tqdm`: Para barra de progreso (`pip install tqdm`).
  - `pandas`: Para exportar HTML/CSV avanzado (`pip install pandas`).

No se requiere instalación de paquetes adicionales vía pip para el núcleo (todo built-in o requests).

## Instalación

1. Clona o descarga el repositorio:
   ```
   git clone <tu-repo-url>
   cd mtg-price-tracker
   ```

2. Instala dependencias opcionales:
   ```
   pip install tqdm pandas
   ```

3. Crea los archivos de configuración (ver sección **Setup**).

## Setup

### Tokens y Archivos Requeridos

- **tk**: Archivo de texto con tu token de API de CardTrader (una línea: `tu_token_aqui`). Obténlo en tu cuenta de CardTrader > API.
  
- **wishlist** (opcional): Archivo de texto con IDs de wishlists (uno por línea, ignora comentarios con `#`). Ejemplo:
  ```
  123456789  # Mi wishlist principal
  987654321  # Wishlist secundaria
  ```

- **telegram_token.txt** (opcional): Token de bot de Telegram (crea un bot con @BotFather).
  
- **telegram_chat_id.txt** (opcional): ID del chat para notificaciones (obténlo con @userinfobot).

### Configuración

Edita `data/config.json` (se crea automáticamente con valores por defecto):
```json
{
    "keep_days": 365,  // Días para mantener histórico (default: 1 año)
    "max_workers": 3   // Hilos para procesamiento paralelo (ajusta según tu máquina)
}
```

- Ejecuta el script una vez para inicializar `data/precios_historicos.db` (SQLite).

**Migración opcional**: Si tienes un `precios_historicos.json` viejo, descomenta `migrate_from_json()` en `main()` para importarlo.

## Uso

1. Asegúrate de tener `tk` en la raíz del proyecto.

2. Ejecuta el script:
   ```
   python main.py
   ```

3. Ingresa el ID de wishlist (o presiona Enter para usar `wishlist`):
   - Procesa cartas únicas, consulta APIs, actualiza histórico.
   - Muestra progreso (con tqdm si instalado).

4. Al final:
   - Genera CSV/HTML por wishlist en `outputs/wishlist/<ID>/`.
   - CSV global si múltiples wishlists en `outputs/global/`.
   - Envía sugerencias por Telegram (si configurado).
   - Limpia histórico viejo automáticamente.

**Ejemplo de salida en consola:**
```
Procesando: black-lotus (nuevo)
  Debug - Específica: set=lea, num=1
  Encontrada impresión específica: LEA #1
  Total productos válidos encontrados: 5
Mejor: Unlimited - ES - Near Mint - Yes - 1500.00€ (2 copias disponibles)
Histórico: Max 1600.00€ | Mediana 1450.00€ | Q1 1400.00€ | Min 1300.00€ | 🟢 Barato (cerca del Q1)
  SUGERENCIA: ¡Compra black-lotus! Precio actual (1500.00€) está en Q1 del histórico (1400.00€).
```

## Salidas

- **CSV**: `outputs/wishlist/<ID>/<nombre_wishlist>_resultados.csv` – Columnas completas (nombre, expansión, precio, histórico, etc.).
- **HTML**: `outputs/wishlist/<ID>/<nombre_wishlist>_resumen.html` – Tabla resumida con colores (requiere pandas). Abre en navegador.
- **Histórico**: `data/precios_historicos.db` – Exportable a CSV completo con `export_historical()` (se ejecuta auto al final).
- **Global**: Si múltiples wishlists, resúmenes en `outputs/global/`.

**Ejemplo de tabla HTML (resumida):**

| nombre_carta | min_historico | max_historico | mediana_historico | q1_historico | precio_euros | indicador_color      |
|--------------|---------------|---------------|-------------------|--------------|--------------|----------------------|
| black-lotus | 1300.00      | 1600.00      | 1450.00          | 1400.00     | 1500.00     | 🟢 Barato           |
| dual-land   | 200.00       | 500.00       | 350.00           | 250.00      | 400.00      | 🟡 Medio            |

## Sugerencias de Compra

- Se generan si hay ≥2 ejecuciones (para Q1).
- Criterios: Precio ≤ Q1 histórico o ≥20% descuento vs mediana.
- Enviadas por Telegram con formato HTML (negritas, emojis).

## Solución de Problemas

- **Error 429 (Rate Limit)**: El script incluye retries y delays (0.1-0.3s). Si persiste, reduce `max_workers` en config.
- **No printings en Scryfall**: Verifica slug de carta (e.g., `black-lotus`). Fallback a todas las impresiones.
- **DB locked**: Multihilo usa locks; si error, reduce workers o ejecuta secuencial.
- **Sin pandas/tqdm**: Funciona sin ellos, pero sin HTML/progreso.
- **Migración JSON**: Descomenta en `main()` para importar datos viejos.
- **Tamaño DB >500MB**: Aumenta `keep_days` o borra manual `precios_historicos.db`.

## Contribuciones

¡Bienvenidas! Abre issues o PRs para mejoras (e.g., más APIs, filtros).

## Licencia

MIT License – Ver [LICENSE](LICENSE) para detalles. (Crea el archivo si subes a GitHub).
