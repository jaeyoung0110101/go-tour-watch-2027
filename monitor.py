import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://tickets.scopelyexplore.com/events/#/eventlisting?appId=pgo"
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


def check():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    with webdriver.Chrome(options=options) as driver:
        driver.set_page_load_timeout(35)
        driver.get(URL)
        for cookie in json.loads(os.environ["TICKET_COOKIES"]):
            driver.add_cookie(cookie)
        driver.get(URL)
        ready = os.environ["READY_TEXT"].strip()
        if not ready:
            raise ValueError("Missing logged-in list marker")
        def list_text(browser):
            text = browser.find_element(By.TAG_NAME, "body").text
            return text if ready in text else False
        text = WebDriverWait(driver, 30).until(list_text)
        # Keep nearby listing text so a later sale-status change can trigger again.
        lines = text.splitlines()
        matches = []
        for index, line in enumerate(lines):
            if any(re.search(pattern, line, re.I) for pattern in CITIES.values()):
                matches.extend(lines[max(0, index-2):index+6])
        return "\n".join(matches)


if __name__ == "__main__":
    import hashlib
    state_file = Path(".monitor-state")
    previous = state_file.read_text().strip() if state_file.exists() else ""
    try:
        listing = check()
    except Exception:
        if previous != "error" or os.getenv("TEST") == "true":
            notify("티켓 목록 확인 실패. 로그인 상태를 확인해 주세요.")
        state_file.write_text("error")
    else:
        state = hashlib.sha256(listing.encode()).hexdigest()
        if listing and (state != previous or os.getenv("TEST") == "true"):
            notify("LA 또는 카오슝 관련 티켓 목록이 표시되거나 변경됐습니다. 눌러 판매 여부를 확인하세요.")
        elif os.getenv("TEST") == "true" or previous == "error":
            notify("로그인된 이벤트 목록 확인 성공. 알림 연결이 정상입니다.")
        state_file.write_text(state)
