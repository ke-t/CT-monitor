import re
import time
import sys
import os
import select
import random  # Para gaussiana
from playwright.sync_api import sync_playwright, expect  # Nueva: Playwright sync
from bs4 import BeautifulSoup

# Importa config para delays
from config import DELAY_MIN_SEC, DELAY_MAX_SEC, DELAY_MEAN_SEC, DELAY_STD_SEC

def random_delay(min_sec=None, max_sec=None, mean_sec=None, std_sec=None):
    """
    Delay aleatorio con distribución gaussiana (truncada a min/max).
    """
    min_d = min_sec or DELAY_MIN_SEC
    max_d = max_sec or DELAY_MAX_SEC
    mean_d = mean_sec or DELAY_MEAN_SEC
    std_d = std_sec or DELAY_STD_SEC
    
    delay = random.gauss(mean_d, std_d)
    delay = max(min_d, min(delay, max_d))
    
    time.sleep(delay)

def timed_input(prompt, timeout=60):
    """
    Input con timeout.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        line = sys.stdin.readline().strip()
        return line
    else:
        print()
        return ""

def scrape_wishlist(url):
    """
    Scraping con Playwright (corregido: usa launch_persistent_context para perfil).
    """
    print(f"[DEBUG] Iniciando scrape de {url} con Playwright")
    playwright = None
    browser = None
    context = None
    page = None
    try:
        playwright = sync_playwright().start()
        
        # Config browser: Chromium con perfil persistente y stealth
        chrome_profile_path = os.getenv('CHROME_PROFILE_PATH', os.getenv('CHROME_PROFILE_DIR', '/home/poio/.config/google-chrome/Default'))
        headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        
        # User-agents rotados para anti-detección
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        selected_ua = random.choice(user_agents)
        
        # Viewport random
        width = random.randint(1200, 1920)
        height = random.randint(800, 1080)
        
        # FIX: Usa launch_persistent_context para --user-data-dir
        browser_type = playwright.chromium
        context = browser_type.launch_persistent_context(
            user_data_dir=chrome_profile_path,
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                f'--window-size={width},{height}',
            ],
            viewport={'width': width, 'height': height},
            user_agent=selected_ua,
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Mode': 'navigate',
            }  # Anti-bot headers
        )
        page = context.new_page()  # Nueva página en el contexto persistente
        
        print("[DEBUG] Playwright iniciado con perfil persistente y stealth. Debería estar logueado.")
        
        # Navega y wait inicial
        print(f"[DEBUG] Accediendo a: {url}")
        page.goto(url, wait_until='networkidle')  # Espera JS/network
        random_delay(min_sec=2, max_sec=5)  # Post-load gaussiano
        
        # Wait para tabla (dinámico, como antes)
        print("[DEBUG] Esperando tabla con cartas (máx 30s)...")
        page.wait_for_selector('.deck-table-rows .deck-table-row', timeout=30000)
        print("[DEBUG] Tabla detectada.")
        
        # Chequea login
        if "login" in page.url.lower() or "iniciar sesion" in page.content().lower():
            print("[WARNING] No logueado. Loguéate manualmente en la ventana.")
            return None

        # Hover en featured card
        print("[DEBUG] Hover en '.card.mx-auto.card-featured'...")
        try:
            featured_locator = page.locator('.card.mx-auto.card-featured')
            featured_locator.wait_for(state='visible', timeout=10000)
            featured_locator.hover()
            print("[DEBUG] Hover realizado. Esperando tooltips (máx 5s)...")
            
            # FIX: Chequeo con JS evaluate para serializable
            def check_non_zero_in_tooltip():
                return page.evaluate("""
                    () => {
                        const tooltips = document.querySelectorAll('.deck-table-row__price [data-original-title]');
                        return Array.from(tooltips).some(el => {
                            const title = el.getAttribute('data-original-title') || el.textContent;
                            const match = title.match(/€(\\d+\\.\\d{2})/);
                            return match && parseFloat(match[1]) > 0;
                        });
                    }
                """)
            
            page.wait_for_function(check_non_zero_in_tooltip, timeout=5000)
            print("[DEBUG] Tooltips/precios estabilizados.")
            random_delay(1, 2)
        except Exception as hover_err:
            print(f"[WARNING] Hover timeout o error: {hover_err}. Continuando...")

        # Click en botón optimize si enabled
        print("[DEBUG] Buscando botón '.btn.btn-success'...")
        try:
            button_locator = page.locator('.btn.btn-success')
            button_locator.wait_for(state='visible', timeout=10000)
            if button_locator.is_enabled():
                print("[DEBUG] Botón enabled: Click...")
                button_locator.click()
                print("[DEBUG] Click realizado. Esperando precios actualizados (máx 30s)...")
                
                # FIX: has_non_zero_price con JS evaluate
                def has_non_zero_price():
                    return page.evaluate("""
                        () => {
                            const rows = document.querySelectorAll('.deck-table-row');
                            for (let row of rows.slice(0, 5)) {
                                const priceEl = row.querySelector('.deck-table-row__price .row .col');
                                if (priceEl) {
                                    const text = priceEl.textContent;
                                    const match = text.match(/€(\\d+\\.\\d{2})/);
                                    if (match && parseFloat(match[1]) > 0) return true;
                                }
                                const tooltipEl = row.querySelector('.deck-table-row__price .row[data-original-title]');
                                if (tooltipEl) {
                                    const title = tooltipEl.getAttribute('data-original-title');
                                    const match = title.match(/€(\\d+\\.\\d{2})/);
                                    if (match && parseFloat(match[1]) > 0) return true;
                                }
                            }
                            return false;
                        }
                    """)
                
                # Wait para al menos un precio >0
                page.wait_for_function(has_non_zero_price, timeout=30000)
                print("[DEBUG] Precios no cero detectados post-click.")
            else:
                print("[DEBUG] Botón disabled: Esperando...")
                random_delay(min_sec=3, max_sec=6)
                
            # Polling si no hay precios aún (gaussiano)
            print("[DEBUG] Verificando precios (máx 90s, poll 1.5-3s)...")
            max_wait = 90
            waited = 0
            while waited < max_wait and not has_non_zero_price():
                random_delay(min_sec=1.5, max_sec=3)
                waited += random.uniform(1.5, 3)  # Aprox acumulado
            if has_non_zero_price():
                print(f"[DEBUG] Precios OK en ~{waited:.1f}s.")
            else:
                print("[WARNING] Timeout en precios.")
                
        except Exception as btn_err:
            print(f"[WARNING] Botón no encontrado o error: {btn_err}")

        # Extrae con BS4 (igual que antes)
        print("[DEBUG] Extrayendo cartas...")
        soup = BeautifulSoup(page.content(), 'html.parser')
        
        # Limpia no deseados
        for unwanted in soup.find_all(['footer', 'header', 'nav', '.site-footer', 'aside']):
            unwanted.decompose()
        
        container = soup.select_one('.deck-table-rows')
        if not container:
            print("[ERROR] No contenedor. Guardando debug.html...")
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            return soup.get_text(separator='\n', strip=True)
        
        print(f"[DEBUG] {len(container.select('.deck-table-row'))} rows encontradas.")
        
        texto = ""
        rows = container.select('.deck-table-row')
        for row in rows:
            name_div = row.select_one('.deck-table-row__name span')
            if not name_div:
                continue
            nombre = name_div.get_text(strip=True)
            if len(nombre) < 3 or not re.match(r'^[A-Z]', nombre):
                continue
            
            if any(word in nombre.lower() for word in ['sesión', 'zero', 'comprar', 'ahora', 'cerrar', 'cardtrader', 'box', 'tin', 'mazzi', 'bustine', 'dadi', 'tapetes']):
                continue
            
            texto += f"{nombre}\n"
            texto += "Indiferente\nIndiferenteEN+ESDEENESFRITJPPTZH-CN\nIndiferenteNear MintSlightly PlayedModerately PlayedPlayedPoor\nIndiferenteSíNo\n"
            
            price_div = row.select_one('.deck-table-row__price .row .col')
            precio = '€0.00'
            if price_div:
                cell_text = price_div.get_text(strip=True)
                match = re.search(r'€(\d+\.\d{2})', cell_text)
                if match:
                    precio = match.group(0)
                else:
                    tooltip_row = row.select_one('.deck-table-row__price .row[data-original-title]')
                    if tooltip_row:
                        tooltip = tooltip_row.get('data-original-title', '')
                        match = re.search(r'€(\d+\.\d{2})', tooltip)
                        if match:
                            precio = match.group(0)
            
            texto += f"{precio}\n\n"
            if precio != '€0.00':
                print(f"[DEBUG] Carta: {nombre} | {precio}")
            else:
                print(f"[WARNING] Precio cero: {nombre}")
        
        if not texto.strip():
            texto = soup.get_text(separator='\n', strip=True)
            print("[DEBUG] Fallback texto completo.")
        
        print(f"[DEBUG] Texto final: {len(texto)} chars.")
        return texto
        
    except Exception as e:
        print(f"[ERROR] Scrape Playwright: {e}")
        return None
    finally:
        if page:
            random_delay(1, 3)  # Final gaussiano
            context.close()  # Cierra contexto persistente
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        print("[DEBUG] Playwright cerrado.")