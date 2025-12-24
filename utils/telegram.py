import requests
import os

def send_telegram_message(message):
    """
    Envía un mensaje a Telegram.
    """
    token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT')
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("[INFO] Mensaje Telegram enviado.")
        else:
            print(f"[ERROR] Fallo Telegram: {response.status_code}")
    else:
        print("[WARNING] No TELEGRAM_TOKEN o TELEGRAM_CHAT.")