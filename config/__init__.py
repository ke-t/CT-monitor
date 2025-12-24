"""
Módulo de configuración. Carga variables de .env.
"""
from dotenv import load_dotenv

def load_config():
    """
    Carga el archivo .env.
    """
    load_dotenv()
    print("[DEBUG] Configuración cargada desde .env.")