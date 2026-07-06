#!/usr/bin/env python3
"""
Scraper pour annuaire-du-ecommerce.com
Usage: python scrape_annuaire.py <categorie> <total_boutiques>
Exemple: python scrape_annuaire.py sante-beaute 680

Récupère pour chaque boutique : nom, catégorie, note, nb_avis, ville (si dispo),
description, site web externe, email (extrait du JSON-LD FAQPage).
Throttle : 1 requête toutes les 5 secondes.
Sauvegarde en JSON dans ./output/<categorie>.json
"""

import sys
import json
import re
import time
import math
import os
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.annuaire-du-ecommerce.com"
PER_PAGE = 24
THROTTLE_SECONDS = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProspectionBot/1.0)"
}

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def throttled_get(url):
    """GET avec throttle de 5s après chaque requête (succès ou échec)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        return resp
    except requests.RequestException as e:
        print(f"  [ERREUR] {url} -> {e}")
        return None
    finally:
        time.sleep(THROTTLE_SECONDS)


def get_listing_slugs(categorie, page):
    """Récupère les slugs /site/{slug} d'une page de listing."""
    if page == 1:
        url = f"{BASE_URL}/sites/{categorie}"
    else:
        url = f"{BASE_URL}/sites/{categorie}?page={page}"

    resp = throttled_get(url)
    if resp is None or resp.status_code != 200:
        print(f"  [SKIP] page {page} statut {resp.status_code if resp else 'N/A'}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    slugs = []
    for a in soup.select("a.group.block[href^='/site/']"):
        href = a.get("href", "")
        slug = href.replace("/site/", "").strip("/")
        if slug:
            slugs.append(slug)
    return slugs


def extract_jsonld(soup):
    """Extrait tous les blocs JSON-LD de la page en une liste de dicts."""
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
            if isinstance(data, list):
                blocks.extend(data)
            else:
                blocks.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def find_email(jsonld_blocks, raw_html):
    """Cherche un email dans le bloc FAQPage (texte de la réponse 'Comment contacter...'),
    puis fallback sur tout le JSON-LD sérialisé, puis fallback regex sur le HTML brut."""
    # 1. Bloc FAQPage en priorité (c'est là qu'il se trouve dans le format observé)
    for block in jsonld_blocks:
        if block.get("@type") == "FAQPage":
            for question in block.get("mainEntity", []):
                answer_text = question.get("acceptedAnswer", {}).get("text", "")
                match = EMAIL_REGEX.search(answer_text)
                if match:
                    return match.group(0)

    # 2. Fallback : n'importe quel bloc JSON-LD sérialisé
    for block in jsonld_blocks:
        block_str = json.dumps(block, ensure_ascii=False)
        match = EMAIL_REGEX.search(block_str)
        if match:
            return match.group(0)

    # 3. Fallback ultime : regex sur tout le HTML brut
    match = EMAIL_REGEX.search(raw_html)
    if match:
        return match.group(0)

    return None


def find_ville(soup):
    """Cherche un éventuel champ 'Ville' dans les informations clés (optionnel selon les fiches)."""
    label = soup.find(string=re.compile(r"^\s*Ville\s*$"))
    if label:
        parent_p = label.find_parent("p")
        if parent_p:
            container = parent_p.find_parent("div")
            if container:
                value_div = container.find("div", class_=re.compile("text-sm"))
                if value_div:
                    return value_div.get_text(strip=True)
    return None


def scrape_boutique(slug, categorie):
    """Scrape une fiche boutique complète, en priorisant le JSON-LD 'Store'."""
    url = f"{BASE_URL}/site/{slug}"
    resp = throttled_get(url)
    if resp is None or resp.status_code != 200:
        print(f"  [SKIP] {slug} statut {resp.status_code if resp else 'N/A'}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    jsonld_blocks = extract_jsonld(soup)

    store_block = next((b for b in jsonld_blocks if b.get("@type") == "Store"), {})

    nom = store_block.get("name")
    if not nom:
        h1 = soup.find("h1")
        nom = h1.get_text(strip=True) if h1 else slug

    description = store_block.get("description")
    site_externe = store_block.get("url")

    rating = store_block.get("aggregateRating", {}) or {}
    note = rating.get("ratingValue")
    nb_avis = rating.get("reviewCount")

    email = find_email(jsonld_blocks, resp.text)
    ville = find_ville(soup)

    return {
        "slug": slug,
        "nom": nom,
        "categorie": categorie,
        "note": note,
        "nb_avis": nb_avis,
        "ville": ville,
        "description": description,
        "site_externe": site_externe,
        "email": email,
        "fiche_url": url,
    }


def main():
    if len(sys.argv) != 3:
        print("Usage: python scrape_annuaire.py <categorie> <total_boutiques>")
        sys.exit(1)

    categorie = sys.argv[1]
    total = int(sys.argv[2])
    nb_pages = math.ceil(total / PER_PAGE)

    print(f"=== Scraping catégorie '{categorie}' — {total} boutiques sur {nb_pages} pages ===")

    all_slugs = []
    for page in range(1, nb_pages + 1):
        print(f"[Listing] page {page}/{nb_pages}")
        slugs = get_listing_slugs(categorie, page)
        all_slugs.extend(slugs)
        print(f"  -> {len(slugs)} boutiques trouvées (total cumulé: {len(all_slugs)})")

    print(f"\n=== {len(all_slugs)} slugs collectés, début du scraping des fiches ===\n")

    resultats = []
    for i, slug in enumerate(all_slugs, 1):
        print(f"[Fiche {i}/{len(all_slugs)}] {slug}")
        data = scrape_boutique(slug, categorie)
        if data:
            resultats.append(data)
            email_status = "OK" if data["email"] else "PAS D'EMAIL"
            print(f"  -> {data['nom']} | email: {email_status}")

        if i % 20 == 0:
            os.makedirs("output", exist_ok=True)
            with open(f"output/{categorie}.json", "w", encoding="utf-8") as f:
                json.dump(resultats, f, ensure_ascii=False, indent=2)

    os.makedirs("output", exist_ok=True)
    output_path = f"output/{categorie}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

    nb_avec_email = sum(1 for r in resultats if r["email"])
    print(f"\n=== TERMINÉ ===")
    print(f"Total boutiques scrapées : {len(resultats)}")
    if resultats:
        print(f"Avec email trouvé : {nb_avec_email} ({nb_avec_email/len(resultats)*100:.1f}%)")
    print(f"Sauvegardé dans : {output_path}")


if __name__ == "__main__":
    main()
