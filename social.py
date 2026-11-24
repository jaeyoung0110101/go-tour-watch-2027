import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from monitor import notify, page

TRAINERS = "https://trainersgo.com/events/pokemon-go-tour/"
SOURCES = {
    "TrainersGO": TRAINERS,
    "Leek Duck (Bluesky)": "https://bsky.app/profile/did:plc:yntdoq7z6rllxwldtlgndeza/rss",
    "Pokémon GO Hub": "https://pokemongohub.net/feed/",
}
TOUR = re.compile(r"go\s*tour|tour.{0,20}alola|alola.{0,20}tour|kaohsiung|los angeles|高雄", re.I)
SALE = re.compile(r"ticket|on sale|sold out|early.bird|on.sale|presale|pre.sale|售票|開賣", re.I)


def read_feed(url):
    if url == TRAINERS:
        cards = page(url).select("#schedule-block a.schedule_item[href]")
        if not cards:
            raise ValueError("Empty TrainersGO Tour list")
        return [(urljoin(url, card["href"]), card.get("title") or card.select_one("h3").get_text(strip=True), "") for card in cards]
    request = Request(url, headers={"User-Agent": "GoTourWatch/1.0 (public RSS reader)"})
    with urlopen(request, timeout=25) as response:
        root = ElementTree.fromstring(response.read())
    items = []
    for item in root.findall("./channel/item"):
        link = item.findtext("link", "").strip()
        title = item.findtext("title", "").strip()
        summary = BeautifulSoup(item.findtext("description", ""), "html.parser").get_text(" ", strip=True)
        if link.startswith("https://"):
            items.append((link, title, summary))
    if not items:
        raise ValueError("Empty feed")
    return items


def run():
    path = Path(".social-state")
    seen = json.loads(path.read_text()) if path.exists() else {}
    failed = False
    for name, url in SOURCES.items():
        try:
            posts = read_feed(url)
        except Exception as error:
            print(name, str(error), file=sys.stderr)
            failed = True
            continue
        known = seen.get(name)
        for link, title, summary in reversed(posts):
            text = title + " " + summary
            if known is None or link in known:
                continue
            if url == TRAINERS and re.search(r"alola|2027|kaohsiung|los [áa]ngeles", text, re.I):
                notify("TrainersGO 투어 일정 등록 · " + title, link)
            elif TOUR.search(text) and SALE.search(text):
                notify(f"현장 티켓 관련 보도 · {name}\n{(title or summary)[:220]}", link)
        seen[name] = list(dict.fromkeys([p[0] for p in posts] + (known or [])))[:300]
        print(name, len(posts), "posts checked")
    path.write_text(json.dumps(seen, sort_keys=True))
    return int(failed)


if __name__ == "__main__":
    sys.exit(run())
