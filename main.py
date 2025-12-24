#!/usr/bin/env python3
import time
import sys
import os
from dotenv import load_dotenv

# Imports modulares
from config import load_config
from scraper.browser import scrape_wishlist, timed_input
from scraper.parser import parsear_cartas
from db.handler import guardar_historial, analizar_ejemplo
from db import generar_html_stats  # Para generar el HTML
from utils.telegram import send_telegram_message

load_config()  # Carga .env

def procesar_wishlist(wishlist_id):
    """
    Procesa una wishlist individual.
    """
    url = f"https://www.cardtrader.com/wishlists/{wishlist_id}"
    print(f"\n=== Procesando Wishlist {wishlist_id} ===")
    print(f"[DEBUG] URL: {url}")
    
    texto = scrape_wishlist(url)
    if texto:
        print("Extraído.")
    else:
        print("Falló.")
        return 0
    
    if not texto:
        return 0
    
    print("[DEBUG] Parse...")
    cartas = parsear_cartas(texto)
    total_cartas = len(cartas)
    if cartas:
        print(f"¡Éxito! {len(cartas)} cartas:")
        for c in cartas[:10]:
            print(f"  {c['Nombre']} | €{c['Precio']:.2f}")
        if len(cartas) > 10:
            print(f"  ... +{len(cartas)-10}.")
        
        guardar_historial(cartas, wishlist_id=wishlist_id)
        analizar_ejemplo()
        generar_html_stats()  # Genera el HTML actualizado
    else:
        print("No válidas. Revisa si los precios se cargaron (busca €0.00 en el log).")
        total_cartas = 0
    
    return total_cartas

if __name__ == "__main__":
    print("¡Bienvenido!")
    wishlist_id = timed_input("ID wishlist (o Enter para procesar archivo wishlists.txt): ", 60)
    
    if wishlist_id:
        # Modo single
        num_cartas = procesar_wishlist(wishlist_id)
        send_telegram_message(f"Scraping completado para wishlist {wishlist_id}. Cartas: {num_cartas}")
    else:
        # Modo batch: lee de wishlists.txt
        wishlist_file = 'wishlists.txt'
        if not os.path.exists(wishlist_file):
            print(f"[ERROR] Archivo {wishlist_file} no encontrado. Crea uno con IDs uno por línea.")
            sys.exit(1)
        
        with open(wishlist_file, 'r') as f:
            ids = [line.strip() for line in f if line.strip()]
        
        if not ids:
            print("[ERROR] No hay IDs en el archivo.")
            sys.exit(1)
        
        interval_minutes = int(os.getenv('INTERVAL_MINUTES', 60))
        
        while True:
            print(f"[INFO] Procesando {len(ids)} wishlists de {wishlist_file}...")
            total_cartas_global = 0
            for idx, wid in enumerate(ids, 1):
                print(f"\n--- {idx}/{len(ids)} ---")
                cartas_procesadas = procesar_wishlist(wid)
                total_cartas_global += cartas_procesadas
                print(f"Cartas procesadas en esta wishlist: {cartas_procesadas}")
            
            print(f"\n¡Proceso completado! Total cartas únicas procesadas: {total_cartas_global}")
            send_telegram_message(f"Scraping batch completado! Total cartas: {total_cartas_global}")
            
            print(f"[INFO] Esperando {interval_minutes} minutos antes de siguiente ciclo...")
            time.sleep(interval_minutes * 60)