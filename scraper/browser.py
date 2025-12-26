import re
import time
import sys
import os
import select
import random  # Nueva: Para delays y randomizaciones
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
from selenium_stealth import stealth  # Nueva: Para enmascaramiento

def random_delay(min_sec=0.5, max_sec=2.0):
    """Delay aleatorio para simular comportamiento humano."""
    time.sleep(random.uniform(min_sec, max_sec))

def human_scroll(driver):
    """Scroll aleatorio para más realismo (opcional)."""
    scroll_amount = random.randint(200, 800)
    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
    random_delay(0.5, 1.5)

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

def create_driver():
    """Crea el driver con enmascaramiento stealth y randomizaciones."""
    options = Options()
    # Binary y profile via env
    options.binary_location = os.getenv('CHROME_BINARY_PATH', '/usr/bin/google-chrome-stable')
    chrome_profile_path = os.getenv('CHROME_PROFILE_PATH', '/home/poio/.config/google-chrome/Default')
    options.add_argument(f'--user-data-dir={chrome_profile_path}')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # Headless via env (nuevo: más flexible)
    if os.getenv('HEADLESS', 'true').lower() == 'true':
        options.add_argument('--headless')
    
    # Anti-detección básica
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Randomiza user-agent
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    options.add_argument(f'--user-agent={random.choice(user_agents)}')
    
    # Randomiza tamaño de ventana
    width = random.randint(1200, 1920)
    height = random.randint(800, 1080)
    options.add_argument(f'--window-size={width},{height}')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Aplica stealth
    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
    )
    
    # Oculta webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def scrape_wishlist(url):
    """
    Realiza el scraping de una wishlist (versión mejorada con stealth y delays random).
    """
    print(f"[DEBUG] Iniciando scrape de {url}")
    driver = None
    try:
        driver = create_driver()
        print("[DEBUG] Chrome iniciado con stealth y tu perfil. Debería estar logueado.")
    except Exception as e:
        print(f"[ERROR] Fallo al iniciar Chrome: {e}")
        return None
    
    try:
        print(f"[DEBUG] Accediendo a: {url}")
        driver.get(url)
        random_delay(2, 5)  # Delay random post-load para simular usuario
        
        # Espera dinámica para carga inicial y tabla
        print("[DEBUG] Esperando carga inicial y tabla con cartas (máx 30s)...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".deck-table-rows .deck-table-row"))
            )
            print("[DEBUG] Tabla con cartas detectada.")
            human_scroll(driver)  # Scroll aleatorio para realismo
        except TimeoutException:
            print("[ERROR] No se cargó la tabla con cartas en 30s. Revisa conexión o sitio.")
            return None

        # Chequea login
        if "login" in driver.current_url.lower() or "iniciar sesion" in driver.page_source.lower():
            print("[WARNING] No logueado. Loguéate en la ventana ahora.")
            return None

        # Hover en .card.mx-auto.card-featured
        print("[DEBUG] Buscando y hover en '.card.mx-auto.card-featured'...")
        try:
            featured_card = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card.mx-auto.card-featured")))
            ActionChains(driver).move_to_element(featured_card).perform()
            print("[DEBUG] Hover realizado. Esperando estabilización de tooltips (máx 5s)...")
            
            # Wait para tooltips/precios (con fallback)
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text)
                    for elem in d.find_elements(By.CSS_SELECTOR, ".deck-table-row__price [data-original-title]")
                    if float(re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text).group(1)) > 0
                    if re.search(r'€(\d+\.\d{2})', elem.get_attribute('data-original-title') or elem.text)
                ) or True
            )
            print("[DEBUG] Tooltips/precios estabilizados.")
            random_delay(1, 2)  # Pausa humana post-hover
        except TimeoutException:
            print("[WARNING] Elemento '.card.mx-auto.card-featured' no encontrado o timeout en hover. Continuando...")
        except Exception as hover_err:
            print(f"[ERROR] Error en hover: {hover_err}")

        # Busca botón '.btn.btn-success'
        print("[DEBUG] Buscando botón '.btn.btn-success'...")
        try:
            optimize_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".btn.btn-success")))
            is_enabled = optimize_button.is_enabled()
            print(f"[DEBUG] Botón encontrado. ¿Enabled? {is_enabled}")
            
            if is_enabled:
                print("[DEBUG] Botón enabled: Click en él...")
                optimize_button.click()
                print("[DEBUG] Click realizado. Esperando precios actualizados (máx 30s)...")
                
                def has_non_zero_price(driver):
                    page_text = driver.page_source
                    soup_temp = BeautifulSoup(page_text, 'html.parser')
                    container_temp = soup_temp.select_one('.deck-table-rows')
                    if container_temp:
                        rows_temp = container_temp.select('.deck-table-row')
                        for row_temp in rows_temp[:5]:  # Chequea solo primeras 5
                            price_div_temp = row_temp.select_one('.deck-table-row__price .row .col')
                            if price_div_temp:
                                cell_text_temp = price_div_temp.get_text(strip=True)
                                match_temp = re.search(r'€(\d+\.\d{2})', cell_text_temp)
                                if match_temp and float(match_temp.group(1)) > 0:
                                    return True
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
                random_delay(3, 6)  # Delay extra si disabled
            
            # Loop de polling con delays random
            print("[DEBUG] Verificando precios no cero en tabla (máx 90s, poll random 1.5-3s)...")
            max_wait = 90
            waited = 0
            has_non_zero = has_non_zero_price(driver)
            while waited < max_wait and not has_non_zero:
                time.sleep(random.uniform(1.5, 3))  # Poll random
                waited += random.uniform(1.5, 3)
                has_non_zero = has_non_zero_price(driver)
            if has_non_zero:
                print(f"[DEBUG] Precios no cero OK en ~{waited:.1f}s.")
            else:
                print("[WARNING] Timeout esperando precios no cero. Continuando con lo disponible.")
                
        except TimeoutException:
            print("[WARNING] Botón '.btn.btn-success' no encontrado. Continuando sin optimizar...")
        except Exception as btn_err:
            print(f"[ERROR] Error con botón: {btn_err}")

        # Extrae con BS4
        print("[DEBUG] Extrayendo cartas con estructura de divs...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Limpia no deseados
        for unwanted in soup.find_all(['footer', 'header', 'nav', '.site-footer', 'aside']):
            unwanted.decompose()
        
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
            random_delay(1, 3)  # Delay final antes de cerrar
            driver.quit()
            print("[DEBUG] Chrome cerrado.")