#!/usr/bin/env python3
"""
Importe les fichiers JSON scrapés dans la table Supabase 'prospects'.

Usage:
    pip install requests
    python import_to_supabase.py mode.json maison-deco.json sante-beaute.json bijoux.json

Utilise l'upsert (ON CONFLICT slug) donc tu peux relancer le script plusieurs fois
sans créer de doublons.
"""

import sys
import json
import requests

SUPABASE_URL = "https://gkethvpxhqkxxdtgajpn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdrZXRodnB4aHFreHhkdGdhanBuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMyOTE3NjIsImV4cCI6MjA5ODg2Nzc2Mn0.-rgiMWnGw0bxueAzBwl0o-MdxivrgpmRKvVz2PA2jkc"

BATCH_SIZE = 200


def import_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n=== {filepath} : {len(data)} entrées ===")

    # Nettoyage : ne garder que les champs attendus par la table
    rows = []
    for d in data:
        rows.append({
            "slug": d.get("slug"),
            "nom": d.get("nom"),
            "categorie": d.get("categorie"),
            "note": d.get("note"),
            "nb_avis": d.get("nb_avis"),
            "ville": d.get("ville"),
            "description": d.get("description"),
            "site_externe": d.get("site_externe"),
            "email": d.get("email"),
            "fiche_url": d.get("fiche_url"),
        })

    url = f"{SUPABASE_URL}/rest/v1/prospects"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # upsert sur conflit (slug est UNIQUE)
    }

    total_inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        resp = requests.post(url, headers=headers, json=batch, timeout=30)
        if resp.status_code in (200, 201):
            total_inserted += len(batch)
            print(f"  Batch {i // BATCH_SIZE + 1} : {len(batch)} lignes OK")
        else:
            print(f"  [ERREUR] Batch {i // BATCH_SIZE + 1} : statut {resp.status_code}")
            print(f"  {resp.text[:500]}")

    print(f"  -> Total importé pour ce fichier : {total_inserted}/{len(rows)}")
    return total_inserted


def main():
    if len(sys.argv) < 2:
        print("Usage: python import_to_supabase.py fichier1.json [fichier2.json ...]")
        sys.exit(1)

    grand_total = 0
    for filepath in sys.argv[1:]:
        grand_total += import_file(filepath)

    print(f"\n=== TERMINÉ : {grand_total} lignes importées au total ===")


if __name__ == "__main__":
    main()
