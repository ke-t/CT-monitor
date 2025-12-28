#!/usr/bin/env python3
import time
import sys
import os
import pandas as pd  # Para filtrar DataFrame
import random  # Para gaussiana en interval
from dotenv import load_dotenv

# Cargar .env (incluye DEBUG_MODE)
load_dotenv()

# Flag de debug con modos
DEBUG_MODE = os.getenv('DEBUG_MODE', 'off').lower()

# Imports modulares
from config import load_config  # Ya no llamamos aquí; se auto-carga en config/__init__.py
from db.handler import inicializar_bd, guardar_historial, analizar_ejemplo, get_significant_price_changes
from db import generar_html_stats  # Para generar el HTML
from scraper.browser import scrape_wishlist, timed_input
from scraper.parser import parsear_cartas
from utils.telegram import send_telegram_message

# load_config()  # REMOVIDO: Ahora se auto-ejecuta en config/__init__.py al importar

inicializar_bd()  # Inicializa BD con nuevo schema (UNIQUE, DATETIME)

# Import para umbral (disponible post-auto-carga)
from config import PRICE_DROP_THRESHOLD

def procesar_wishlist(wishlist_id):
    """
    Procesa una wishlist individual.
    """
    url = f"https://www.cardtrader.com/wishlists/{wishlist_id}"
    print(f"\n=== Procesando Wishlist {wishlist_id} ===")
    if DEBUG_MODE == 'debug':
        print(f"[DEBUG] URL: {url}")
    
    texto = scrape_wishlist(url)
    if texto:
        print("Extraído.")
    else:
        print("Falló.")
        return 0
    
    if not texto:
        return 0
    
    if DEBUG_MODE == 'debug':
        print("[DEBUG] Parse...")
    cartas = parsear_cartas(texto)
    total_cartas = len(cartas)
    if cartas:
        print(f"¡Éxito! {len(cartas)} cartas:")
        for c in cartas[:10]:
            print(f"  {c['Nombre']} | €{c['Precio']:.2f}")
        if len(cartas) > 10:
            print(f"  ... +{len(cartas)-10}.")
        
        # Nombres actuales para filtro en stats
        current_names = [c['Nombre'] for c in cartas]
        
        inserted = guardar_historial(cartas, wishlist_id=wishlist_id)
        
        # Chequea bajadas y alerta si hay (solo última iteración)
        cambios = get_significant_price_changes()
        cambios_wishlist = cambios[cambios['wishlist_id'] == int(wishlist_id)] if not cambios.empty else pd.DataFrame()
        if not cambios_wishlist.empty:
            if DEBUG_MODE == 'debug':
                print("[DEBUG] ¡Intentando enviar Telegram detallado!")
            mensaje = f"¡Bajadas significativas en wishlist {wishlist_id} (<Q1 o >{PRICE_DROP_THRESHOLD*100:.0f}%, última iteración)!\n\n"
            for _, row in cambios_wishlist.iterrows():
                pct_str = f" (bajada {row['pct_drop']*100:.1f}%)" if row['pct_drop'] > PRICE_DROP_THRESHOLD else ""
                mensaje += f"• {row['nombre']}: Actual €{row['precio']:.2f}{pct_str}, Q1 €{row['q1_precio']:.2f}, Min €{row['min_precio']:.2f}, Max €{row['max_precio']:.2f}\n"
            send_telegram_message(mensaje)
            if DEBUG_MODE == 'debug':
                print(f"[DEBUG] Enviado Telegram con {len(cambios_wishlist)} bajadas para {wishlist_id}.")
        else:
            if DEBUG_MODE == 'debug':
                print(f"[DEBUG] Sin bajadas significativas en esta wishlist (última iteración). Skip Telegram detallado.")
        
        # Pasa nombres actuales para filtro en stats (prioridad sobre wishlist_id)
        analizar_ejemplo(inserted, current_names=current_names)
        generar_html_stats()  # Genera el HTML actualizado
    else:
        print("No válidas. Revisa si los precios se cargaron (busca €0.00 en el log).")
        total_cartas = 0
        analizar_ejemplo(0, current_names=[])  # Skip stats si no hay cartas
        generar_html_stats()
    
    return total_cartas

if __name__ == "__main__":
    print("¡Bienvenido!")
    wishlist_id = timed_input("ID wishlist (o Enter para procesar archivo wishlists.txt): ", 60)
    
    if wishlist_id:
        # Modo single
        num_cartas = procesar_wishlist(wishlist_id)
        # Mensaje de cierre SIEMPRE con detalles si hay bajadas
        if DEBUG_MODE == 'debug':
            print("[DEBUG] ¡Intentando enviar resumen single!")
        cambios = get_significant_price_changes()
        cambios_wishlist = cambios[cambios['wishlist_id'] == int(wishlist_id)] if not cambios.empty else pd.DataFrame()
        if not cambios_wishlist.empty:
            mensaje = f"Scraping completado para wishlist {wishlist_id}. {len(cambios_wishlist)} bajadas en última iteración.\n\nDetalles:\n"
            for _, row in cambios_wishlist.iterrows():
                pct_str = f" (bajada {row['pct_drop']*100:.1f}%)" if row['pct_drop'] > PRICE_DROP_THRESHOLD else ""
                mensaje += f"• {row['nombre']}: Actual €{row['precio']:.2f}{pct_str}, Q1 €{row['q1_precio']:.2f}, Min €{row['min_precio']:.2f}, Max €{row['max_precio']:.2f}\n"
            send_telegram_message(mensaje)
        else:
            send_telegram_message(f"Scraping completado para wishlist {wishlist_id}. Cartas: {num_cartas}. Sin bajadas significativas en última iteración.")
    else:
        # Modo batch: lee de wishlists.txt con soporte para comentarios (#)
        wishlist_file = 'wishlists.txt'
        if not os.path.exists(wishlist_file):
            print(f"[ERROR] Archivo {wishlist_file} no encontrado. Crea uno con IDs uno por línea.")
            sys.exit(1)
        
        with open(wishlist_file, 'r') as f:
            ids = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        
        if not ids:
            print("[ERROR] No hay IDs válidos en el archivo (ignora líneas con # para comentarios).")
            sys.exit(1)
        
        # Usa config para interval gaussiano y umbral (ya disponible por auto-load)
        from config import INTERVAL_MIN_MIN, INTERVAL_MAX_MIN, INTERVAL_MEAN_MIN, INTERVAL_STD_MIN, PRICE_DROP_THRESHOLD
        
        while True:
            if DEBUG_MODE in ['info', 'debug']:
                print(f"[INFO] Procesando {len(ids)} wishlists de {wishlist_file}...")
            total_cartas_global = 0
            for idx, wid in enumerate(ids, 1):
                print(f"\n--- {idx}/{len(ids)} ---")
                cartas_procesadas = procesar_wishlist(wid)
                total_cartas_global += cartas_procesadas
                print(f"Cartas procesadas en esta wishlist: {cartas_procesadas}")
            
            # Mensaje de cierre SIEMPRE en batch con detalles
            if DEBUG_MODE == 'debug':
                print("[DEBUG] ¡Intentando enviar resumen batch!")
            cambios_global = get_significant_price_changes()
            if not cambios_global.empty:
                mensaje = f"Scraping batch completado! Total cartas: {total_cartas_global}. {len(cambios_global)} bajadas significativas en última iteración (<Q1 o >{PRICE_DROP_THRESHOLD*100:.0f}%).\n\nDetalles:\n"
                for _, row in cambios_global.iterrows():
                    pct_str = f" (bajada {row['pct_drop']*100:.1f}%)" if row['pct_drop'] > PRICE_DROP_THRESHOLD else ""
                    mensaje += f"• {row['nombre']} (wishlist {row['wishlist_id']}): Actual €{row['precio']:.2f}{pct_str}, Q1 €{row['q1_precio']:.2f}, Min €{row['min_precio']:.2f}, Max €{row['max_precio']:.2f}\n"
                send_telegram_message(mensaje)
                print(f"\n¡Proceso completado! Total cartas procesadas: {total_cartas_global}. {len(cambios_global)} bajadas globales en última iteración.")
            else:
                print(f"\n¡Proceso completado! Total cartas procesadas: {total_cartas_global}. Sin bajadas significativas.")
                send_telegram_message(f"Batch completado sin bajadas en última iteración. Total cartas procesadas: {total_cartas_global}.")
            
            # Intervalo gaussiano truncado
            interval_min = INTERVAL_MIN_MIN * 60  # En segundos
            interval_max = INTERVAL_MAX_MIN * 60
            interval_mean = INTERVAL_MEAN_MIN * 60
            interval_std = INTERVAL_STD_MIN * 60
            
            delay_interval = random.gauss(interval_mean, interval_std)
            delay_interval = max(interval_min, min(delay_interval, interval_max))
            
            if DEBUG_MODE in ['info', 'debug']:
                print(f"[INFO] Esperando intervalo gaussiano: ~{delay_interval / 60:.1f} minutos antes de siguiente ciclo...")
            time.sleep(delay_interval)