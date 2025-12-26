import requests
import os
import time

def send_telegram_message(message):
    """
    Envía un mensaje a Telegram con manejo de errores, truncado y parse mode opcional.
    """
    if not message or not isinstance(message, str):
        print("[WARNING] Mensaje inválido (vacío o no string). No se envía.")
        return

    token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT')
    parse_mode = os.getenv('TELEGRAM_PARSE_MODE')  # e.g., 'HTML' o 'Markdown'

    if not token or not chat_id:
        print("[WARNING] Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT en .env.")
        return

    # Truncar si excede 4096 chars
    if len(message) > 4096:
        message = message[:4093] + "..."
        print(f"[INFO] Mensaje truncado a 4096 chars.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }
    if parse_mode:
        data["parse_mode"] = parse_mode

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()  # Lanza excepción para 4xx/5xx

        json_response = response.json()
        if json_response.get('ok'):
            print("[INFO] Mensaje Telegram enviado exitosamente.")
        else:
            error_msg = json_response.get('description', 'Error desconocido')
            print(f"[ERROR] Fallo en Telegram API: {error_msg}")
            if 'rate' in error_msg.lower():  # Detección básica de rate limit
                print("[INFO] Rate limit detectado. Esperando 60s...")
                time.sleep(60)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error de red en Telegram: {e}")
    except Exception as e:
        print(f"[ERROR] Error inesperado en Telegram: {e}")

    # Sleep básico para rate limiting (ajustable)
    time.sleep(2)