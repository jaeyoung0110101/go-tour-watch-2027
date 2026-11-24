import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://tickets.scopelyexplore.com/events/#/eventlisting?appId=pgo&returnUrl=%2Feventlisting"
CITIES = {"LA": r"Los Angeles|로스앤젤레스|洛杉磯", "카오슝": r"Kaohsiung|가오슝|카오슝|高雄"}


def notify(text):
    endpoint = os.environ["NTFY_URL"].strip()
    if urlsplit(endpoint).scheme != "https":
        raise SystemExit("ntfy requires an HTTPS topic URL")
    headers = {"Title": "Pokemon GO Tour", "Priority": "high", "Click": URL}
    if os.getenv("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NTFY_TOKEN"]
    try:
        with urlopen(Request(endpoint, data=text.encode(), headers=headers), timeout=15) as response:
            if not 200 <= response.status < 300:
                raise ValueError()
    except Exception:
        raise SystemExit("ntfy delivery failed") from None


def page(url):
    with urlopen(url, timeout=20) as response:
        return BeautifulSoup(response.read(), "html.parser")


def check():
    index = "https://pokemongo.com/en/featured-in-person-events"
    records = {}
    pages = {}
    for tag in page(index).select('script[type="application/ld+json"]'):
        event = json.loads(tag.get_text())
        name = event.get("name", "")
        if name not in {"GO Tour: Kaohsiung", "GO Tour: Los Angeles"}:
            continue
        href = urljoin(index, event["url"])
        if urlsplit(href).hostname != "pokemongo.com":
            records[name] = [href, event.get("offers")]
            continue
        if href not in pages:
            doc = page(href)
            body = doc.find("article") or doc.find("main")
            if not body or not body.get_text(strip=True):
                raise ValueError("Empty event page")
            pages[href] = [body.get_text(" ", strip=True),
                           [a["href"] for a in body.select("a[href]")]]
        records[name] = [href, event.get("offers"), pages[href]]
    if len(records) != 2:
        raise ValueError("Missing city")
    return json.dumps(records, sort_keys=True)


if __name__ == "__main__":
    import hashlib
    state_file = Path(".monitor-state")
    previous = state_file.read_text().strip() if state_file.exists() else ""
    try:
        listing = check()
    except Exception:
        if previous != "error" or os.getenv("TEST") == "true":
            notify("공식 행사 페이지 확인 실패.")
        state_file.write_text("error")
    else:
        state = hashlib.sha256(listing.encode()).hexdigest()
        if previous and previous != state:
            notify("LA·카오슝 공식 행사 안내가 변경됐습니다. 눌러 티켓 판매 여부를 확인하세요.")
        elif os.getenv("TEST") == "true" or previous == "error":
            notify("공식 행사 안내 확인 성공. ntfy 연결이 정상입니다.")
        state_file.write_text(state)
