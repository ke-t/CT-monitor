import re
import time
import sys
import os
import select
import random  # Para gaussiana
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Importa config para delays (después de load_config en main)
from config import DELAY_MIN_SEC, DELAY_MAX_SEC, DELAY_MEAN_SEC, DELAY_STD_SEC

def random_delay(min_sec=None, max_sec=None, mean_sec=None, std_sec=None):
    """
    Delay aleatorio con distribución gaussiana (truncada a min/max).
    - Si no pasas params, usa los de .env.
    - Simula pausas humanas: mayoría cerca de la media.
    """
    # Usa params locales o globales de config
    min_d = min_sec or DELAY_MIN_SEC
    max_d = max_sec or DELAY_MAX_SEC
    mean_d = mean_sec or DELAY_MEAN_SEC
    std_d = std_sec or DELAY_STD_SEC
    
    # Genera gaussiano y clippea
    delay = random.gauss(mean_d, std_d)
    delay = max(min_d, min(delay, max_d))  # Trunca al rango
    
    time.sleep(delay)
    # Opcional: print(f"[DEBUG] Delay aplicado: {delay:.2f}s (gaussiana)")  # Descomenta para debug

def timed_input(prompt, timeout=60):
    """
    Input con timeout. Si no se ingresa nada en X seg, retorna vacío.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        line = sys.stdin.readline().strip()
        return line
    else:
        print()  # Nueva línea para limpiar
        return ""

def scrape_wishlist(url):
    """
    Realiza el scraping de una wishlist (versión simple, sin extras).
    """
    print(f"[DEBUG] Iniciando scrape de {url}")
    options = Options()
    # Nueva: Env var para binary (fallback hardcoded)
    options.binary_location = os.getenv('CHROME_BINARY_PATH', '/usr/bin/google-chrome-stable')
    # Nueva: Env var para profile (era hardcoded)
    chrome_profile_path = os.getenv('CHROME_PROFILE_PATH', os.getenv('CHROME_PROFILE_DIR', '/home/poio/.config/google-chrome/Default'))
    options.add_argument(f'--user-data-dir={chrome_profile_path}')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    if os.getenv('HEADLESS', 'true').lower() == 'true':
        options.add_argument('--headless')  # Headless activado

    service = Service(ChromeDriverManager().install())
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        print("[DEBUG] Chrome iniciado con tu perfil. Debería estar logueado.")
    except Exception as e:
        print(f"[ERROR] Fallo al iniciar Chrome: {e}")
        return None
    
    try:
        print(f"[DEBUG] Accediendo a: {url}")
        driver.get(url)
        random_delay(min_sec=2, max_sec=5)  # Delay random post-load (gaussiano)
        
        # REEMPLAZO: Espera dinámica para carga inicial y tabla (en vez de sleep(10))
        print("[DEBUG] Esperando carga inicial y tabla con cartas (máx 30s)...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".deck-table-rows .deck-table-row"))
            )
            print("[DEBUG] Tabla con cartas detectada.")
        except TimeoutException:
            print("[ERROR] No se cargó la tabla con cartas en 30s. Revisa conexión o sitio.")
            return None

        # Chequea login (igual)
        if "login" in driver.current_url.lower() or "iniciar sesion" in driver.page_source.lower():
            print("[WARNING] No logueado. Loguéate en la ventana ahora.")
            return None

        # Hover en .card.mx-auto.card-featured (igual, pero con wait después)
        print("[DEBUG] Buscando y hover en '.card.mx-auto.card-featured'...")
        try:
            featured_card = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card.mx-auto.card-featured")))
            ActionChains(driver).move_to_element(featured_card).perform()
            print("[DEBUG] Hover realizado. Esperando estabilización de tooltips (máx 5s)...")
            
            # REEMPLAZO: Wait para que precios/tooltips se muestren (en vez de sleep(3))
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text)
                    for elem in d.find_elements(By.CSS_SELECTOR, ".deck-table-row__price [data-original-title]")
                    if float(re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text).group(1)) > 0
                    if re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text)
                ) or True  # Fallback si no hay, solo espera 1s mínimo
            )
            print("[DEBUG] Tooltips/precios estabilizados.")
            random_delay(1, 2)  # Pausa humana post-hover (gaussiano)
        except TimeoutException:
            print("[WARNING] Elemento '.card.mx-auto.card-featured' no encontrado o timeout en hover. Continuando...")
        except Exception as hover_err:
            print(f"[ERROR] Error en hover: {hover_err}")

        # REEMPLAZO: Eliminamos sleep(5); la siguiente wait lo cubre
        print("[DEBUG] Buscando botón '.btn.btn-success'...")
        try:
            optimize_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".btn.btn-success")))
            is_enabled = optimize_button.is_enabled()
            print(f"[DEBUG] Botón encontrado. ¿Enabled? {is_enabled}")
            
            if is_enabled:
                print("[DEBUG] Botón enabled: Click en él...")
                optimize_button.click()
                print("[DEBUG] Click realizado. Esperando precios actualizados (máx 30s)...")
                
                # REEMPLAZO: Wait dinámica para al menos un precio no cero (en vez de sleep(10))
                def has_non_zero_price(driver):
                    page_text = driver.page_source
                    soup_temp = BeautifulSoup(page_text, 'html.parser')
                    container_temp = soup_temp.select_one('.deck-table-rows')
                    if container_temp:
                        rows_temp = container_temp.select('.deck-table-row')
                        for row_temp in rows_temp[:5]:  # Chequea solo primeras 5 para velocidad
                            # Chequea precio principal
                            price_div_temp = row_temp.select_one('.deck-table-row__price .row .col')
                            if price_div_temp:
                                cell_text_temp = price_div_temp.get_text(strip=True)
                                match_temp = re.search(r'€(\d+\.\d{2})', cell_text_temp)
                                if match_temp and float(match_temp.group(1)) > 0:
                                    return True
                            # Fallback tooltip
                            tooltip_row_temp = row_temp.select_one('.deck-table-row__price .row[data-original-title]')
                            if tooltip_row_temp:
                                tooltip_temp = tooltip_row_temp.get('data-original-title', '')
                                match_temp = re.search(r'€(\d+\.\d{2})', tooltip_temp)
                                if match_temp and float(match_temp.group(1)) > 0:
                                    return True
                    return False
                
                try:
                    WebDriverWait(driver, 30).until(has_non_zero_price)
                    print("[DEBUG] Al menos un precio no cero detectado después del click.")
                except TimeoutException:
                    print("[WARNING] No se detectaron precios no cero en 30s después del click. Continuando...")
            else:
                print("[DEBUG] Botón disabled: Esperando que carguen los precios...")
                random_delay(min_sec=3, max_sec=6)  # Delay extra si disabled (gaussiano)
            
            # REEMPLAZO: Loop de polling más eficiente (random 1.5-3s en vez de 2s fijo, máx 90s total)
            print("[DEBUG] Verificando precios no cero en tabla (máx 90s, poll random 1.5-3s)...")
            max_wait = 90
            waited = 0
            has_non_zero = has_non_zero_price(driver)  # Chequeo inicial
            while waited < max_wait and not has_non_zero:
                random_delay(min_sec=1.5, max_sec=3)  # Poll gaussiano corto
                waited += random.uniform(1.5, 3)  # Aprox para acumular (usa uniform para simplicidad)
                has_non_zero = has_non_zero_price(driver)
            if has_non_zero:
                print(f"[DEBUG] Precios no cero OK en ~{waited:.1f}s.")
            else:
                print("[WARNING] Timeout esperando precios no cero. Continuando con lo disponible.")
                
        except TimeoutException:
            print("[WARNING] Botón '.btn.btn-success' no encontrado. Continuando sin optimizar...")
        except Exception as btn_err:
            print(f"[ERROR] Error con botón: {btn_err}")

        # Extrae con estructura específica de divs (simple, sin extras)
        print("[DEBUG] Extrayendo cartas con estructura de divs...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Limpia elementos no deseados
        for unwanted in soup.find_all(['footer', 'header', 'nav', '.site-footer', 'aside']):
            unwanted.decompose()
        
        # Busca contenedor de rows
        container = soup.select_one('.deck-table-rows')
        if not container:
            print("[ERROR] No .deck-table-rows encontrada. Guardando HTML para debug...")
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            print("HTML guardado en 'debug.html'. Revisa manualmente.")
            return soup.get_text(separator='\n', strip=True)
        
        print(f"[DEBUG] Contenedor encontrado con {len(container.select('.deck-table-row'))} rows.")
        
        texto = ""
        rows = container.select('.deck-table-row')
        for row in rows:
            # Extrae nombre del .deck-table-row__name
            name_div = row.select_one('.deck-table-row__name span')
            if not name_div:
                continue
            nombre = name_div.get_text(strip=True)
            if len(nombre) < 3 or not re.match(r'^[A-Z]', nombre):
                continue
            
            # Filtra no-cartas
            if any(word in nombre.lower() for word in ['sesión', 'zero', 'comprar', 'ahora', 'cerrar', 'cardtrader', 'box', 'tin', 'mazzi', 'bustine', 'dadi', 'tapetes']):
                continue
            
            # Bloques placeholder (simple)
            texto += f"{nombre}\n"
            texto += "Indiferente\nIndiferenteEN+ESDEENESFRITJPPTZH-CN\nIndiferenteNear MintSlightly PlayedModerately PlayedPlayedPoor\nIndiferenteSíNo\n"
            
            # Extrae precio del .deck-table-row__price
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
                print(f"[DEBUG] Carta extraída: {nombre} | {precio}")
            else:
                print(f"[WARNING] Precio cero para {nombre} - posiblemente no cargado.")
        
        if not texto.strip():
            texto = soup.get_text(separator='\n', strip=True)
            print("[DEBUG] Fallback a texto completo.")
        
        print(f"[DEBUG] Texto final: {len(texto)} chars. Primeras 300: {texto[:300]}...")
        return texto
        
    except Exception as e:
        print(f"[ERROR] Scrape: {e}")
        return None
    finally:
        if driver:
            random_delay(1, 3)  # Delay final antes de cerrar (gaussiano)
            driver.quit()
            print("[DEBUG] Chrome cerrado.")