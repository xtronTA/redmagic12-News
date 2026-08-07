"""
Vigilante de anuncio del RedMagic 12.

Fuentes:
- Google News (prensa)
- Reddit (búsqueda general)
- Twitter/X oficial @redmagicgaming (vía Nitter, best-effort/inestable)
- Canal oficial de YouTube de REDMAGIC (vía RSS, sin API key)
- Página oficial redmagic.gg (best-effort)

Cada fuente está protegida individualmente: si una falla, las demás siguen
funcionando y el script no se cae completo (esto es lo que arregla los
crashes que tenías antes).

Guarda el estado (lo ya visto) en seen.json, que se commitea de vuelta
al repo desde el workflow de GitHub Actions, así no se repiten avisos.

Nota sobre Instagram: no existe forma gratuita ni confiable de vigilar
posts de una cuenta sin iniciar sesión o pagar la API oficial de Meta.
Para eso, lo más confiable es activar la campanita de notificaciones en
la app de Instagram para @redmagicgaming directamente.
"""

import os
import json
import re
import smtplib
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from urllib.parse import quote

import requests

SEEN_FILE = "seen.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (redmagic12-watcher/1.0)"}
KEYWORDS = ("redmagic 12", "red magic 12")

QUERY = '"RedMagic 12" OR "Red Magic 12"'
NEWS_RSS_URL = f"https://news.google.com/rss/search?q={quote(QUERY)}&hl=es-419&gl=MX&ceid=MX:es"
REDDIT_URL = f"https://www.reddit.com/search.json?q={quote('RedMagic 12')}&sort=new&limit=10"

# Canal oficial verificado de REDMAGIC en YouTube
YOUTUBE_CHANNEL_ID = "UCqX5t6irpHLRUBqf_0hKAvg"
YOUTUBE_RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"

OFFICIAL_SITE_URL = "https://www.redmagic.gg/en/us/news"

# Cuenta oficial en Twitter/X: @redmagicgaming, vía Nitter (espejo no
# oficial e inestable). Si todas las instancias fallan, se omite esta
# fuente sin romper el script.
NITTER_INSTANCES = [
    "https://nitter.net/redmagicgaming/rss",
    "https://nitter.privacydev.net/redmagicgaming/rss",
]


def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def mentions_redmagic12(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in KEYWORDS)


def fetch_news() -> list[tuple[str, str, str]]:
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
    resp = requests.get(REDDIT_URL, timeout=20, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
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


def fetch_youtube_official() -> list[tuple[str, str, str]]:
    """Solo videos del canal oficial verificado de REDMAGIC."""
    resp = requests.get(YOUTUBE_RSS_URL, timeout=20, headers=HEADERS)
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.content)
    items = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        if title_el is None or link_el is None:
            continue
        title = title_el.text or ""
        link = link_el.get("href", "")
        if mentions_redmagic12(title) and link:
            items.append(("YouTube oficial REDMAGIC", title, link))
    return items


def fetch_official_site() -> list[tuple[str, str, str]]:
    """Best-effort: busca menciones de RedMagic 12 en la página oficial."""
    resp = requests.get(OFFICIAL_SITE_URL, timeout=20, headers=HEADERS)
    resp.raise_for_status()
    html = resp.text
    items = []
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{0,200})</a>', html, re.IGNORECASE):
        href, text = match.group(1), match.group(2)
        if mentions_redmagic12(text):
            link = href if href.startswith("http") else f"https://www.redmagic.gg{href}"
            items.append(("Página oficial REDMAGIC", text.strip(), link))
    return items


def fetch_twitter_official() -> list[tuple[str, str, str]]:
    """Best-effort vía Nitter (espejo no oficial e inestable de Twitter/X)."""
    for base_url in NITTER_INSTANCES:
        try:
            resp = requests.get(base_url, timeout=15, headers=HEADERS)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                if title_el is None or link_el is None:
                    continue
                title = title_el.text or ""
                if mentions_redmagic12(title):
                    items.append(("Twitter/X oficial REDMAGIC", title, link_el.text or ""))
            return items  # si una instancia funcionó, no probamos las demás
        except Exception:
            continue  # prueba la siguiente instancia
    return []  # todas las instancias fallaron, se omite esta fuente


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


def safe_fetch(name: str, fn) -> list[tuple[str, str, str]]:
    """Ejecuta una función de fetch protegida: si falla, avisa y sigue
    en vez de tumbar todo el script."""
    try:
        return fn()
    except Exception as e:
        print(f"Error consultando {name}: {e}")
        return []


def main() -> None:
    first_run = not os.path.exists(SEEN_FILE)
    seen = load_seen()

    items = []
    items += safe_fetch("Google News", fetch_news)
    items += safe_fetch("Reddit", fetch_reddit)
    items += safe_fetch("YouTube oficial", fetch_youtube_official)
    items += safe_fetch("Página oficial", fetch_official_site)
    items += safe_fetch("Twitter/X oficial", fetch_twitter_official)

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
