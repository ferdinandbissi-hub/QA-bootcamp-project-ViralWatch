"""
fetch_who_bulletins.py — ViralWatch Day 4 (setup step for the NLP session)

Downloads real WHO Disease Outbreak News (DON) bulletins for the 2026
Bundibugyo virus outbreak and saves the extracted article text as plain
.txt files, ready for the NER/classification pipeline.

Run with:
    source venv/bin/activate
    python src/fetch_who_bulletins.py
"""

import requests
from bs4 import BeautifulSoup
from pathlib import Path
import time

OUT_DIR = Path("data/who_bulletins")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Real WHO DON bulletins for this outbreak, oldest to most recent.
# (Found via who.int/emergencies/disease-outbreak-news -- more can be added
# the same way if your team wants a bigger corpus.)
BULLETINS = {
    "DON602_2026-05-17": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON602",
    "DON603_2026-05-21": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON603",
    "DON605_2026-05-29": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON605",
    "DON606_2026-06-08": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON606",
    "DON612_2026-07-03": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON612",
    "DON613_2026-07-17": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON613",
    "DON614_2026-08-01": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON614",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (ViralWatch bootcamp project; educational use)"}


def extract_article_text(html: str) -> str:
    """Pull just the DON article body (Situation at a glance -> WHO advice),
    skipping WHO's site navigation/header/footer boilerplate."""
    soup = BeautifulSoup(html, "html.parser")
    # WHO's DON pages put the article content in the main content region.
    main = soup.find("main") or soup.find("article") or soup.body
    # Drop nav/header/footer elements if they're nested inside
    for tag in main.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    text = main.get_text(separator="\n", strip=True)
    return text


def main():
    for name, url in BULLETINS.items():
        dest = OUT_DIR / f"{name}.txt"
        if dest.exists():
            print(f"  -> {dest} already exists, skipping")
            continue
        print(f"  -> Downloading {url}")
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        text = extract_article_text(resp.text)
        dest.write_text(text, encoding="utf-8")
        print(f"     Saved {len(text)} characters to {dest}")
        time.sleep(1)  # be polite to WHO's servers


if __name__ == "__main__":
    main()
