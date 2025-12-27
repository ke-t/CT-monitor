import os
from dotenv import load_dotenv

def load_config():
    """
    Carga la configuración desde .env y valida variables requeridas.
    Lanza ValueError si falta alguna para evitar ejecuciones parciales.
    """
    try:
        load_dotenv()
    except Exception as e:
        print(f"[WARNING] Error cargando .env: {e}. Usando defaults donde posible.")
    
    # Lista de variables requeridas (agrega más si necesitas, e.g., 'CHROME_PATH')
    required_vars = [
        'TELEGRAM_TOKEN',      # Token del bot de Telegram
        'TELEGRAM_CHAT',       # ID del chat para alertas
        'CHROME_PROFILE_DIR',  # Directorio de perfil de Chrome (de .env)
        # 'CHROME_DRIVER_PATH'   # Descomenta si usas path fijo en .env
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
    
    # Nuevas vars para delays (opcionales, con defaults y validación)
    # Delays scraping (segundos)
    global DELAY_MIN_SEC, DELAY_MAX_SEC, DELAY_MEAN_SEC, DELAY_STD_SEC
    DELAY_MIN_SEC = float(os.getenv('DELAY_MIN_SEC', 0.5))
    DELAY_MAX_SEC = float(os.getenv('DELAY_MAX_SEC', 3.0))
    DELAY_MEAN_SEC = float(os.getenv('DELAY_MEAN_SEC', (DELAY_MIN_SEC + DELAY_MAX_SEC) / 2))
    DELAY_STD_SEC = float(os.getenv('DELAY_STD_SEC', (DELAY_MAX_SEC - DELAY_MIN_SEC) / 4))
    
    if DELAY_MIN_SEC >= DELAY_MAX_SEC:
        raise ValueError("DELAY_MIN_SEC debe ser < DELAY_MAX_SEC")
    if DELAY_MEAN_SEC < DELAY_MIN_SEC or DELAY_MEAN_SEC > DELAY_MAX_SEC:
        raise ValueError("DELAY_MEAN_SEC debe estar entre MIN y MAX")
    
    # Intervalos batch (minutos)
    global INTERVAL_MIN_MIN, INTERVAL_MAX_MIN, INTERVAL_MEAN_MIN, INTERVAL_STD_MIN
    INTERVAL_MIN_MIN = float(os.getenv('INTERVAL_MIN_MIN', 50))
    INTERVAL_MAX_MIN = float(os.getenv('INTERVAL_MAX_MIN', 70))
    INTERVAL_MEAN_MIN = float(os.getenv('INTERVAL_MEAN_MIN', (INTERVAL_MIN_MIN + INTERVAL_MAX_MIN) / 2))
    INTERVAL_STD_MIN = float(os.getenv('INTERVAL_STD_MIN', (INTERVAL_MAX_MIN - INTERVAL_MIN_MIN) / 4))
    
    if INTERVAL_MIN_MIN >= INTERVAL_MAX_MIN:
        raise ValueError("INTERVAL_MIN_MIN debe ser < INTERVAL_MAX_MIN")
    if INTERVAL_MEAN_MIN < INTERVAL_MIN_MIN or INTERVAL_MEAN_MIN > INTERVAL_MAX_MIN:
        raise ValueError("INTERVAL_MEAN_MIN debe estar entre MIN y MAX")
    
    # Legacy (ignorado)
    os.getenv('INTERVAL_MINUTES', 60)  # Solo para compatibilidad, no usar
    
    print(f"[INFO] Configuración cargada y validada correctamente. {len(required_vars)} vars requeridas OK.")
    print(f"[CONFIG] Delays scraping: Min={DELAY_MIN_SEC}s, Max={DELAY_MAX_SEC}s, Media={DELAY_MEAN_SEC}s, Std={DELAY_STD_SEC}s")
    print(f"[CONFIG] Intervalos batch: Min={INTERVAL_MIN_MIN}min, Max={INTERVAL_MAX_MIN}min, Media={INTERVAL_MEAN_MIN}min, Std={INTERVAL_STD_MIN}min")
    
    # Exporta globals para uso en otros módulos (disponibles post-load)
    globals().update(locals())

# ¡AUTO-CARGA! Ejecuta load_config() al importar el módulo
load_config()