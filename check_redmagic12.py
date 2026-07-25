""""""
Vigilante de anuncio del RedMagic 12.
Revisa Google News, Reddit y YouTube buscando "RedMagic 12" / "Red Magic 12"
y avisa por Discord (webhook) y correo (Gmail) cuando aparece algo nuevo.

Guarda el estado (lo ya visto) en seen.json, que se commitea de vuelta
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
HEADERS = {"User-Agent": "redmagic12-watcher/1.0"}

QUERY = '"RedMagic 12" OR "Red Magic 12"'
NEWS_RSS_URL = f"https://news.google.com/rss/search?q={quote(QUERY)}&hl=es-419&gl=MX&ceid=MX:es"
REDDIT_URL = f"https://www.reddit.com/search.json?q={quote('RedMagic 12')}&sort=new&limit=10"
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3/search"


def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def fetch_news() -> list[tuple[str, str, str]]:
    """Devuelve lista de (fuente, titulo, link)"""
    resp = requests.get(NEWS_RSS_URL, timeout=20, headers=HEADERS)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        if title_el is None or link_el is None:
            continue
        items.append(("Google News", title_el.text or "", link_el.text or ""))
    return items


def fetch_reddit() -> list[tuple[str, str, str]]:
    try:
        resp = requests.get(REDDIT_URL, timeout=20, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error consultando Reddit: {e}")
        return []
    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title", "")
        permalink = post.get("permalink", "")
        if not permalink:
            continue
        link = f"https://reddit.com{permalink}"
        items.append(("Reddit", title, link))
    return items


def fetch_youtube() -> list[tuple[str, str, str]]:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return []  # sin API key, se omite esta fuente
    params = {
        "part": "snippet",
        "q": "RedMagic 12",
        "type": "video",
        "order": "date",
        "maxResults": 10,
        "key": api_key,
    }
    try:
        resp = requests.get(YOUTUBE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error consultando YouTube: {e}")
        return []
    items = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        title = item.get("snippet", {}).get("title", "")
        if not video_id:
            continue
        link = f"https://www.youtube.com/watch?v={video_id}"
        items.append(("YouTube", title, link))
    return items


def send_discord(source: str, title: str, link: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("Aviso: DISCORD_WEBHOOK_URL no configurado, se omite Discord.")
        return
    payload = {"content": f"📱 **[{source}] Noticia sobre RedMagic 12**\n{title}\n{link}"}
    r = requests.post(webhook, json=payload, timeout=15)
    r.raise_for_status()


def send_email(source: str, title: str, link: str) -> None:
    user = os.environ.get("GMAIL_USER")
    pwd = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO", user)
    if not user or not pwd:
        print("Aviso: GMAIL_USER/GMAIL_APP_PASSWORD no configurados, se omite correo.")
        return
    msg = MIMEText(f"Fuente: {source}\n\n{title}\n\n{link}")
    msg["Subject"] = f"🚨 [{source}] Noticia sobre RedMagic 12"
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())


def main() -> None:
    first_run = not os.path.exists(SEEN_FILE)
    seen = load_seen()

    items = []
    items += fetch_news()
    items += fetch_reddit()
    items += fetch_youtube()

    if first_run:
        # Primera ejecución: solo guardamos el estado actual para no
        # notificar cosas viejas que ya existían antes de activar esto.
        save_seen({link for _, _, link in items})
        print(f"Primera ejecución: {len(items)} resultados guardados como estado inicial. No se notifica.")
        return

    new_items = [(s, t, l) for s, t, l in items if l not in seen]

    if not new_items:
        print("Sin novedades sobre el RedMagic 12.")
        return

    for source, title, link in new_items:
        print(f"[{source}] Nuevo: {title}")
        try:
            send_discord(source, title, link)
        except Exception as e:
            print(f"Error enviando a Discord: {e}")
        try:
            send_email(source, title, link)
        except Exception as e:
            print(f"Error enviando correo: {e}")
        seen.add(link)

    save_seen(seen)


if __name__ == "__main__":
    main()
