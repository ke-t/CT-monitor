import re
import time
import sys
import os
import select
import random
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Importa config
from config import DELAY_MIN_SEC, DELAY_MAX_SEC, DELAY_MEAN_SEC, DELAY_STD_SEC

def random_delay(min_sec=None, max_sec=None, mean_sec=None, std_sec=None):
    min_d = min_sec or DELAY_MIN_SEC
    max_d = max_sec or DELAY_MAX_SEC
    mean_d = mean_sec or DELAY_MEAN_SEC
    std_d = std_sec or DELAY_STD_SEC
    delay = random.gauss(mean_d, std_d)
    delay = max(min_d, min(delay, max_d))
    time.sleep(delay)

def timed_input(prompt, timeout=60):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        line = sys.stdin.readline().strip()
        return line
    else:
        print()
        return ""

def count_non_zero_prices(page):
    """FIX: JS robusto - cuenta cualquier €>0 en .deck-table-row__price (fallback amplio)."""
    return page.evaluate("""
        () => {
            const rows = document.querySelectorAll('.deck-table-row');
            let count = 0;
            for (let row of rows) {
                const priceSection = row.querySelector('.deck-table-row__price');
                if (!priceSection) continue;
                // Busca € en cualquier texto/hijo (texto, attr, tooltip)
                const allText = priceSection.textContent + ' ' + 
                                Array.from(priceSection.querySelectorAll('[data-original-title]'))
                                    .map(el => el.getAttribute('data-original-title') || '').join(' ');
                const match = allText.match(/€(\\d+\\.\\d{2})/);
                if (match && parseFloat(match[1]) > 0) count++;
            }
            return {count: count, total: rows.length};
        }
    """)

def has_non_zero_price(page):
    result = count_non_zero_prices(page)
    return result['count'] > 0

def scrape_wishlist(url, max_retries=2):
    for attempt in range(max_retries + 1):
        print(f"[DEBUG] Intento {attempt + 1}/{max_retries + 1} para {url}")
        texto = _scrape_single(url)
        if texto and '€' in texto:  # FIX: Valida si hay al menos algún precio
            return texto
        if attempt < max_retries:
            print(f"[WARNING] Retry {attempt + 1}: <10% precios. Esperando 15s...")
            time.sleep(15)
    return None

def _scrape_single(url):
    playwright = None
    context = None
    page = None
    try:
        playwright = sync_playwright().start()
        
        chrome_profile_path = os.getenv('CHROME_PROFILE_PATH', os.getenv('CHROME_PROFILE_DIR', '/home/poio/.config/google-chrome/Default'))
        headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        if debug_mode:
            headless = False
            print("[DEBUG] Modo debug: Browser visible.")
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        selected_ua = random.choice(user_agents)
        
        width = random.randint(1200, 1920)
        height = random.randint(800, 1080)
        
        browser_type = playwright.chromium
        context = browser_type.launch_persistent_context(
            user_data_dir=chrome_profile_path,
            headless=headless,
            slow_mo=100 if debug_mode else 0,
            args=['--no-sandbox', '--disable-dev-shm-usage', f'--window-size={width},{height}'],
            viewport={'width': width, 'height': height},
            user_agent=selected_ua,
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Mode': 'navigate',
            }
        )
        page = context.new_page()
        
        print("[DEBUG] Playwright iniciado.")
        page.goto(url, wait_until='networkidle')
        random_delay(3, 6)  # FIX: +1s base post-goto
        
        print("[DEBUG] Esperando tabla...")
        page.wait_for_selector('.deck-table-rows .deck-table-row', timeout=30000)
        
        if "login" in page.url.lower() or "iniciar sesion" in page.content().lower():
            print("[WARNING] No logueado.")
            return None

        # Hover (fixed como antes)
        try:
            featured_locator = page.locator('.card.mx-auto.card-featured')
            featured_locator.wait_for(state='visible', timeout=10000)
            featured_locator.hover()
            print("[DEBUG] Hover realizado. Esperando tooltips (máx 5s)...")
            page.wait_for_function(
                expression="() => Array.from(document.querySelectorAll('.deck-table-row__price [data-original-title]')).some(el => el.getAttribute('data-original-title')?.match(/€\\d+\\.\\d{2}/))",
                timeout=5000
            )
            random_delay(1, 2)
        except Exception as e:
            print(f"[WARNING] Hover error: {e}")

        # Botón logic
        button_clicked = False
        min_loaded_pct = 0.5
        is_disabled = True
        try:
            button_locator = page.locator('.btn.btn-success')
            button_locator.wait_for(state='visible', timeout=10000)
            if button_locator.is_enabled():
                print("[DEBUG] Click en Optimize...")
                button_locator.click()
                button_clicked = True
                is_disabled = False
                min_loaded_pct = 0.5
                
                post_click_delay = random.gauss(10, 3)
                post_click_delay = max(5, min(15, post_click_delay))
                print(f"[DEBUG] Sleep post-click: {post_click_delay:.1f}s")
                time.sleep(post_click_delay)
                
                page.wait_for_load_state('networkidle', timeout=45000)
                print("[DEBUG] Network idle.")
            else:
                print("[DEBUG] Botón disabled: Pre-load mode.")
                # FIX: Sleep extendido para JS pre-load (10-25s)
                pre_load_delay = random.gauss(15, 5)
                pre_load_delay = max(10, min(25, pre_load_delay))
                print(f"[DEBUG] Esperando pre-load: {pre_load_delay:.1f}s (para precios sin Optimize)...")
                time.sleep(pre_load_delay)
                min_loaded_pct = 0.1  # FIX: Bajo threshold para disabled
                # Chequeo inicial post-sleep
                if has_non_zero_price(page):
                    print("[DEBUG] Precios detectados post-pre-load. Skip wait.")
                    return _extract_text(page)  # FIX: Extract directo si OK
        except Exception as e:
            print(f"[WARNING] Botón error: {e}")
            is_disabled = True  # Asume disabled en error

        # FIX: Polling adaptado - más largo/frecuente si disabled
        poll_interval = 5 if is_disabled else 10  # Cada 5s si disabled
        max_wait = 240 if is_disabled else 180
        print(f"[DEBUG] Polling (máx {max_wait}s, cada {poll_interval}s, threshold {min_loaded_pct*100}%)...")
        waited = 0
        last_log = 0
        while waited < max_wait:
            result = count_non_zero_prices(page)
            pct = result['count'] / result['total'] if result['total'] > 0 else 0
            if waited - last_log >= poll_interval:
                print(f"[DEBUG] Poll t={waited:.1f}s: {result['count']}/{result['total']} ({pct*100:.0f}%)")
                last_log = waited
            if pct >= min_loaded_pct or result['count'] > 5:  # FIX: O >5 absolutos
                print(f"[DEBUG] Suficiente en {waited:.1f}s: {pct*100:.0f}%.")
                break
            random_delay(2, 4)
            waited += random.uniform(2, 4)
        else:
            print(f"[WARNING] Polling timeout. % final: {pct*100:.0f}%")

        # FIX: Si disabled y bajo %, debug screenshot/HTML
        if is_disabled and pct < 0.2:
            print("[WARNING] Bajo % en disabled: Guardando debug_disabled.html + screenshot.")
            with open('debug_disabled.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            page.screenshot(path='debug_disabled.png')

        # Extract siempre post-polling
        return _extract_text(page)
        
    except Exception as e:
        print(f"[ERROR] Scrape: {e}")
        if 'TargetClosedError' in str(e):
            print("[DEBUG] Ignorando TargetClosed.")
        return None
    finally:
        if page:
            random_delay(1, 3)
            try:
                context.close()
            except:
                pass
        if playwright:
            playwright.stop()
        print("[DEBUG] Playwright cerrado.")

def _extract_text(page):
    """Extrae texto (separado para reuse)."""
    print("[DEBUG] Extrayendo...")
    soup = BeautifulSoup(page.content(), 'html.parser')
    for unwanted in soup.find_all(['footer', 'header', 'nav', '.site-footer', 'aside']):
        unwanted.decompose()
    
    container = soup.select_one('.deck-table-rows')
    if not container:
        with open('debug.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        return soup.get_text(separator='\n', strip=True)
    
    rows = container.select('.deck-table-row')
    print(f"[DEBUG] {len(rows)} rows.")
    
    texto = ""
    zero_count = 0
    total_rows = 0
    bad_words = ['sesión', 'zero', 'comprar', 'ahora', 'cerrar', 'cardtrader', 'box', 'tin', 'mazzi', 'bustine', 'dadi', 'tapetes']
    for row in rows:
        name_div = row.select_one('.deck-table-row__name span')
        if not name_div:
            continue
        nombre = name_div.get_text(strip=True)
        if len(nombre) < 3 or not re.match(r'^[A-Z]', nombre) or any(word in nombre.lower() for word in bad_words):
            continue
        
        total_rows += 1
        texto += f"{nombre}\nIndiferente\nIndiferenteEN+ESDEENESFRITJPPTZH-CN\nIndiferenteNear MintSlightly PlayedModerately PlayedPlayedPoor\nIndiferenteSíNo\n"
        
        # FIX: Extract precio más robusto (cualquier € en section)
        price_section = row.select_one('.deck-table-row__price')
        precio = '€0.00'
        if price_section:
            all_text = price_section.get_text(strip=True)
            tooltip_attrs = ' '.join([el.get('data-original-title', '') for el in price_section.select('[data-original-title]')])
            full_match = re.search(r'€(\d+\.\d{2})', all_text + ' ' + tooltip_attrs)
            if full_match:
                precio = full_match.group(0)
        
        texto += f"{precio}\n\n"
        if precio == '€0.00':
            zero_count += 1
            print(f"[WARNING] Precio cero: {nombre}")
        else:
            print(f"[DEBUG] {nombre}: {precio}")
    
    zero_pct = (zero_count / total_rows * 100) if total_rows > 0 else 0
    print(f"[DEBUG] Extract: {total_rows} cartas, {zero_count} zeros ({zero_pct:.1f}%)")
    if zero_pct > 50:
        print("[WARNING] Alto % zeros: debug_post_extract.html guardado.")
        with open('debug_post_extract.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
    
    if not texto.strip():
        texto = soup.get_text(separator='\n', strip=True)
    
    return texto