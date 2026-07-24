"""
Vigilante de anuncio del RedMagic 12.
Revisa Google News (RSS) buscando noticias sobre "RedMagic 12" / "Red Magic 12"
y avisa por Discord (webhook) y correo (Gmail) cuando aparece algo nuevo.

Guarda el estado (noticias ya vistas) en seen.json, que se commitea de vuelta
al repo desde el workflow de GitHub Actions, así no se repiten avisos.
"""

import os
import json
import smtplib
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from urllib.parse import quote

import requests

SEEN_FILE = "seen.json"
QUERY = '"RedMagic 12" OR "Red Magic 12"'
RSS_URL = f"https://news.google.com/rss/search?q={quote(QUERY)}&hl=es-419&gl=MX&ceid=MX:es"


def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def fetch_news() -> list[tuple[str, str]]:
    resp = requests.get(RSS_URL, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        if title_el is None or link_el is None:
            continue
        items.append((title_el.text or "", link_el.text or ""))
    return items


def send_discord(title: str, link: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("Aviso: DISCORD_WEBHOOK_URL no configurado, se omite Discord.")
        return
    payload = {"content": f"📱 **Noticia sobre RedMagic 12**\n{title}\n{link}"}
    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()


def send_email(title: str, link: str) -> None:
    user = os.environ.get("GMAIL_USER")
    pwd = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO", user)
    if not user or not pwd:
        print("Aviso: GMAIL_USER/GMAIL_APP_PASSWORD no configurados, se omite correo.")
        return
    msg = MIMEText(f"{title}\n\n{link}")
    msg["Subject"] = "🚨 Noticia sobre RedMagic 12"
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())


def main() -> None:
    first_run = not os.path.exists(SEEN_FILE)
    seen = load_seen()

    try:
        items = fetch_news()
    except Exception as e:
        print(f"Error consultando noticias: {e}")
        return

    if first_run:
        # En la primera ejecución solo guardamos el estado actual,
        # para no notificar noticias viejas que ya existían.
        save_seen({link for _, link in items})
        print(f"Primera ejecución: {len(items)} noticias guardadas como estado inicial. No se notifica.")
        return

    new_items = [(t, l) for t, l in items if l not in seen]

    if not new_items:
        print("Sin novedades sobre el RedMagic 12.")
        return

    for title, link in new_items:
        print(f"Nueva noticia detectada: {title}")
        try:
            send_discord(title, link)
        except Exception as e:
            print(f"Error enviando a Discord: {e}")
        try:
            send_email(title, link)
        except Exception as e:
            print(f"Error enviando correo: {e}")
        seen.add(link)

    save_seen(seen)


if __name__ == "__main__":
    main()
