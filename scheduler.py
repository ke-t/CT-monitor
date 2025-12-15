import time
import threading
import queue
from typing import Callable

INPUT_TIMEOUT = 60  # Segundos para esperar input

def input_thread(q: queue.Queue):
    """Hilo para capturar input con posible timeout (prompt vacío para no imprimir)."""
    try:
        inp = input('')  # Prompt vacío: no imprime nada extra
        q.put(inp)
    except (EOFError, KeyboardInterrupt):
        pass

def get_wishlist_id(block: bool = True, timeout: int = INPUT_TIMEOUT) -> str:
    """Obtiene ID con input bloqueante o timeout, SIN interferencia visual."""
    prompt = "ID de wishlist (o Enter para usar wishlists): "
    
    print(f"\nTienes {timeout}s para introducir el ID de la wishlist: ")
    
    if block:
        print(prompt, end='')
        return input().strip()
    
    q = queue.Queue()
    t = threading.Thread(target=input_thread, args=(q,), daemon=True)
    t.start()
    
    # Imprime el prompt SOLO una vez, fijo (sin end='' para nueva línea natural? No, end='' para que el input siga en misma línea)
    print(prompt, end='')
    
    # Loop de timeout: SILENCIOSO, sin prints ni \r
    remaining = timeout
    inp = None
    while remaining > 0:
        try:
            inp = q.get_nowait()
            break
        except queue.Empty:
            pass
        time.sleep(1)  # Espera 1s en silencio
        remaining -= 1
    
    print()  # Nueva línea para avanzar después del input
    
    if inp is not None:
        print("Input recibido: procesando...")
        return inp.strip()
    else:
        print(f"Timeout ({timeout}s): Cargando desde wishlists.")
        return ''

def countdown_sleep(seconds: int, interval: int = 60):
    """Sleep con countdown: Imprime progreso cada 'interval' segundos (default 1 min)."""
    if seconds <= 0:
        return
    
    # Ajusta interval si es muy corto
    display_interval = min(interval, max(1, seconds // 10))  # Mínimo 1s, o 10 updates totales
    
    remaining = seconds
    while remaining > 0:
        mins = remaining // 60
        secs = remaining % 60
        if mins > 0:
            print(f"\rEsperando {mins} min {secs:02d}s hasta la próxima...    ", end='', flush=True)
        else:
            print(f"\rEsperando {secs}s hasta la próxima...    ", end='', flush=True)
        
        sleep_step = min(display_interval, remaining)
        time.sleep(sleep_step)
        remaining -= sleep_step

def run_scheduler(processing_func: Callable[[str | None], int], interval_minutes: int):
    """Bucle principal: Ejecuta cada 'interval_minutes' minutos DESPUÉS de finalizar el procesamiento."""
    print(f"Iniciando scheduler. Se ejecutará cada {interval_minutes} minuto(s) DESPUÉS de finalizar cada proceso.")
    print(f"Para cada ejecución, hay {INPUT_TIMEOUT}s para ingresar un ID de wishlist.")
    print("Si no se ingresa nada, se cargan las wishlists del archivo wishlists.")
    print("Presiona Ctrl+C para detener.\n")
    
    while True:
        start_time = time.time()
        
        # Obtener ID con timeout (no bloqueante, SIN interferencia)
        wishlist_id = get_wishlist_id(block=False, timeout=INPUT_TIMEOUT)
        total_processed = processing_func(wishlist_id)
        
        elapsed = time.time() - start_time
        
        # Sleep con countdown (este SÍ tiene visual, pero no afecta input)
        sleep_time = interval_minutes * 60  # En segundos
        print(f"\nProcesamiento tomó {elapsed/60:.1f} minutos. ", end='')
        countdown_sleep(sleep_time)
        print("\r" + " " * 80 + "\r")  # Limpia la línea final del countdown