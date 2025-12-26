import re
import time
import sys
import select
import os
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
    options.binary_location = os.getenv('CHROME_BINARY_LOCATION')
    chrome_profile_path = os.getenv('CHROME_PROFILE_PATH')
    options.add_argument(f'--user-data-dir={chrome_profile_path}')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
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
        print("[DEBUG] Espera 10s para carga inicial...")
        time.sleep(10)

        # Chequea login
        if "login" in driver.current_url.lower() or "iniciar sesion" in driver.page_source.lower():
            print("[WARNING] No logueado. Loguéate en la ventana ahora.")
            return None  # Sale si no logueado

        # Nueva lógica: Espera que .deck-table-rows tenga contenido (cartas)
        print("[DEBUG] Esperando .deck-table-rows con cartas...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".deck-table-rows .deck-table-row"))
            )
            print("[DEBUG] Tabla con cartas detectada.")
        except TimeoutException:
            print("[ERROR] No se cargó la tabla con cartas. Revisa manualmente.")
            return None

        # Hover en .card.mx-auto.card-featured para mostrar precios ZERO
        print("[DEBUG] Buscando y hover en '.card.mx-auto.card-featured'...")
        try:
            featured_card = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".card.mx-auto.card-featured")))
            ActionChains(driver).move_to_element(featured_card).perform()
            print("[DEBUG] Hover realizado en card-featured. Esperando cambios...")
            time.sleep(3)  # Pausa breve para que se muestren los precios ZERO
        except TimeoutException:
            print("[WARNING] Elemento '.card.mx-auto.card-featured' no encontrado. Continuando sin hover...")
        except Exception as hover_err:
            print(f"[ERROR] Error en hover: {hover_err}")

        # Espera 5s adicionales y comprueba el botón
        print("[DEBUG] Esperando 5s adicionales para estabilizar...")
        time.sleep(5)
        print("[DEBUG] Buscando botón '.btn.btn-success'...")
        try:
            optimize_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".btn.btn-success")))
            is_enabled = optimize_button.is_enabled()
            print(f"[DEBUG] Botón encontrado. ¿Enabled? {is_enabled}")
            
            if is_enabled:
                print("[DEBUG] Botón enabled: Click en él...")
                optimize_button.click()
                print("[DEBUG] Click realizado. Esperando precios en tabla...")
                time.sleep(10)  # Espera inicial fija después del click
            else:
                print("[DEBUG] Botón disabled: Esperando que carguen los precios...")
            
            # Espera precios no cero en la TABLA (unificada y estricta)
            print("[DEBUG] Esperando precios no cero en tabla (máx 3 min)...")
            max_wait = 180
            waited = 10  # Ya esperamos 10s
            has_non_zero = False
            while waited < max_wait and not has_non_zero:
                page_text = driver.page_source
                soup_temp = BeautifulSoup(page_text, 'html.parser')
                container_temp = soup_temp.select_one('.deck-table-rows')
                if container_temp:
                    rows_temp = container_temp.select('.deck-table-row')
                    for row_temp in rows_temp[:10]:  # Chequea solo primeras 10 para velocidad
                        price_div_temp = row_temp.select_one('.deck-table-row__price .row .col')
                        if price_div_temp:
                            cell_text_temp = price_div_temp.get_text(strip=True)
                            match_temp = re.search(r'€(\d+\.\d{2})', cell_text_temp)
                            if match_temp and float(match_temp.group(1)) > 0:
                                has_non_zero = True
                                break
                        # Fallback tooltip
                        tooltip_row_temp = row_temp.select_one('.deck-table-row__price .row[data-original-title]')
                        if tooltip_row_temp:
                            tooltip_temp = tooltip_row_temp.get('data-original-title', '')
                            match_temp = re.search(r'€(\d+\.\d{2})', tooltip_temp)
                            if match_temp and float(match_temp.group(1)) > 0:
                                has_non_zero = True
                                break
                if has_non_zero:
                    print(f"[DEBUG] Precios no cero en tabla OK en {waited}s.")
                    break
                time.sleep(5)
                waited += 5
            else:
                print("[WARNING] Timeout esperando precios no cero en tabla. Continuando con lo que hay (posiblemente 0.00).")
                
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
            driver.quit()
            print("[DEBUG] Chrome cerrado.")