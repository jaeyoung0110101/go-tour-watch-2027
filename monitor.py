import json
import os
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://tickets.scopelyexplore.com/events/#/eventlisting?appId=pgo&returnUrl=%2Feventlisting"
CITIES = {"LA": r"Los Angeles|로스앤젤레스|洛杉磯", "카오슝": r"Kaohsiung|가오슝|카오슝|高雄"}


def notify(text, link=URL):
    endpoint = os.environ["NTFY_URL"].strip()
    if urlsplit(endpoint).scheme != "https":
        raise SystemExit("ntfy requires an HTTPS topic URL")
    headers = {"Title": "Pokemon GO Tour", "Priority": "5", "Click": link}
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


def snapshot():
    result = {"tour": check()}
    for language in ("ko", "en"):
        base = f"https://pokemongo.com/{language}/news"
        anchors = page(base).select("main a[href]")
        news = {}
        for a in anchors:
            link = urljoin(base, a["href"])
            if "/news/" in urlsplit(link).path and urlsplit(link).hostname == "pokemongo.com":
                news[link] = a.get_text(" ", strip=True)
        if not news:
            raise ValueError("Empty news list")
        result[language] = news
        article = page(base + "/save-the-date-go-tour-2027")
        body = article.find("article") or article.find("main")
        result[language + "_article"] = [body.get_text(" ", strip=True), [a["href"] for a in body.select("a[href]")]]
    for key in ("tour", "ko_article", "en_article"):
        result[key] = hashlib.sha256(json.dumps(result[key]).encode()).hexdigest()
    return result


if __name__ == "__main__":
    path = Path(".monitor-state")
    previous = json.loads(path.read_text())
    current = snapshot()
    for lang in ("ko", "en"):
        for link, title in current[lang].items():
            if previous[lang].get(link) != title:
                notify("공식 뉴스 업데이트 · " + title, link)
    if any(current[k] != previous[k] for k in ("tour", "ko_article", "en_article")):
        notify("GO Tour 공식 행사 안내가 변경됐습니다.")
    if current == previous and os.getenv("TEST") == "true":
        notify("공식 뉴스 및 GO Tour 행사 안내 확인 성공.")
    path.write_text(json.dumps(current, sort_keys=True))
