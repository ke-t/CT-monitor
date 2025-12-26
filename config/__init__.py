import os
from dotenv import load_dotenv

def load_config():
    """
    Carga la configuración desde .env y valida variables requeridas.
    Lanza ValueError si falta alguna para evitar ejecuciones parciales.
    """
    load_dotenv()
    
    # Lista de variables requeridas (agrega más si necesitas, e.g., 'CHROME_PATH')
    required_vars = [
        'TELEGRAM_TOKEN',      # Token del bot de Telegram
        'TELEGRAM_CHAT',       # ID del chat para alertas
        'CHROME_PROFILE_DIR',  # Directorio de perfil de Chrome (de .env)
        'CHROME_DRIVER_PATH'   # Descomenta si usas path fijo en .env
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        error_msg = (
            f"¡Error de configuración! Faltan variables obligatorias en .env:\n"
            f"{', '.join(missing_vars)}\n"
            f"Revisa .env.example y completa los valores. Ejemplo:\n"
            f"TELEGRAM_TOKEN=tu_token_aqui\n"
            f"TELEGRAM_CHAT=tu_chat_id_aqui"
        )
        raise ValueError(error_msg)
    
    print(f"[INFO] Configuración cargada y validada correctamente. {len(required_vars)} vars OK.")