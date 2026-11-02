#!/usr/bin/env python3
"""Zapisz komunikaty MPK w pliku JSON dla domowego ekranu TV."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

SOURCE = "https://www.mpk.lodz.pl/rozklady/utrudnienia.jsp"
OUTPUT = Path(os.environ.get("ALERT_OUTPUT", "mpk-alerts.json"))
LINES_PATTERN = re.compile(r"\b(?:[A-Z]{0,2}\d{1,3}[A-Z]?)\b", re.I)
RESOLVED = re.compile(
    r"ruch.{0,35}(?:wznowion|przywrócon)|(?:wznowion|przywrócon).{0,35}ruch|"
    r"komunikacja.{0,30}wznowion|tramwaje.{0,30}(?:kursują|powróciły).{0,30}(?:normalnie|tras)|"
    r"utrudnieni[ae].{0,30}zakończon",
    re.I,
)

def fetch_alerts():
    response = requests.get(
        SOURCE,
        headers={"User-Agent": "EkranLodzDomowy/1.0", "Accept-Language": "pl-PL,pl;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    # Na stronie MPK nagłówek bywa zapisany jako „Nr\\xa0linii” (twarda
    # spacja HTML), a w dni bez komunikatów tabela w ogóle nie występuje.
    # Normalizujemy białe znaki zamiast porównywać surowy HTML.
    def normal(text):
        return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().casefold()

    page_text = normal(soup.get_text(" ", strip=True))
    tables = [
        table for table in soup.find_all("table")
        if "utrudnienie w ruchu" in normal(table.get_text(" ", strip=True))
        and ("nr linii" in normal(table.get_text(" ", strip=True))
             or "zmiana sytuacji" in normal(table.get_text(" ", strip=True)))
    ]

    if not tables:
        if re.search(r"brak(?: aktualnych)? utrudnień(?: w ruchu)?", page_text):
            return []
        title = normal(soup.title.get_text(" ", strip=True)) if soup.title else "(brak tytułu)"
        raise RuntimeError(
            "MPK nie zwróciło tabeli ani potwierdzenia braku utrudnień. "
            f"Tytuł: {title[:90]}; fragment strony: {page_text[-220:]}"
        )
    alerts = []
    for tr in tables[0].find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        lines_text = cells[0].get_text(" ", strip=True)
        lines = sorted(set(LINES_PATTERN.findall(lines_text)), key=lambda x: (len(x), x))
        if not lines or len(lines_text) > 120:
            continue
        message = cells[1].get_text(" ", strip=True)
        update = cells[2].get_text(" ", strip=True)
        if len(message) < 12:
            continue
        if update and RESOLVED.search(update):
            continue
        url = SOURCE
        links = cells[1].find_all("a", href=True)
        if links:
            candidate = urljoin(SOURCE, links[0]["href"])
            if candidate.startswith("https://www.mpk.lodz.pl/"):
                url = candidate
        alerts.append({"lines": lines, "message": message[:340],
                       "update": update[:180], "url": url})
    return alerts[:24]

def main():
    alerts = fetch_alerts()
    payload = {"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "status": "ok", "source": "MPK Łódź", "items": alerts}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Przygotowano", len(alerts), "bieżących komunikatów")

if __name__ == "__main__":
    main()
