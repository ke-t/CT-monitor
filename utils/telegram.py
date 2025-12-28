import requests
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT = os.getenv('TELEGRAM_CHAT')
PARSE_MODE = os.getenv('PARSE_MODE', 'HTML')  # Default HTML

def send_telegram_message(text, max_length=4096):
    """
    Envía mensaje a Telegram con truncado si > max_length.
    - Trunca inteligentemente (última viñeta) y agrega "..." si necesario.
    - Maneja errores 400 con fallback corto.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("[ERROR] TELEGRAM_TOKEN o CHAT faltantes en .env.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Truncado inteligente
    if len(text) > max_length:
        # Busca última \n\n (viñeta) y corta ahí
        last_bullet = text.rfind('\n\n• ')
        if last_bullet > 0:
            truncated = text[:last_bullet + 2] + "... (mensaje truncado; más detalles en logs)"
        else:
            truncated = text[:max_length - 50] + "... (truncado)"
        print(f"[WARNING] Mensaje truncado de {len(text)} a {len(truncated)} chars.")
        text = truncated

    payload = {
        'chat_id': TELEGRAM_CHAT,
        'text': text,
        'parse_mode': PARSE_MODE
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print("[INFO] Mensaje Telegram enviado OK.")
        return True
    except requests.exceptions.HTTPError as e:
        if response.status_code == 400:
            print(f"[ERROR] Telegram 400 Bad Request: {response.json().get('description', 'Desconocido')}")
            # Fallback: Envía versión corta
            short_msg = f"Resumen scraping: {text[:200]}..." if len(text) > 200 else text
            fallback_payload = {'chat_id': TELEGRAM_CHAT, 'text': short_msg}
            try:
                requests.post(url, data=fallback_payload, timeout=10)
                print("[INFO] Fallback corto enviado.")
            except:
                pass
        else:
            print(f"[ERROR] HTTP {response.status_code}: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error en Telegram: {e}")
        return False

# Sleep rate limit (1s entre envíos)
import time
time.sleep(1)