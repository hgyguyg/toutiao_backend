import asyncio

import xml.etree.ElementTree as ET
import httpx
from ddgs import DDGS

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

def _bing_rss_search(query: str):
    with httpx.Client(headers=_HEADERS,timeout=60,follow_redirects=True) as client:
        response = client.get(
            "https://cn.bing.com/search",
            params={"q": query, "format": "rss"},
        )
        response.raise_for_status()

    root = ET.fromstring(response.content)
    results = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        if title or description:
            results.append({"title": title, "url": link, "description": description})
        if len(results) >= 5: break
    return results

def _ddgs_search(query: str) -> list[dict]:

    with DDGS() as ddgs:
        try:
            rows = ddgs.text(query, max_results=5)
        except TypeError:
            rows = ddgs.text(query=query, max_results=5)

    results: list[dict] = []
    for row in rows or []:
        title = str(row.get("title") or "").strip()
        url = str(row.get("href") or row.get("url") or "").strip()
        snippet = str(row.get("body") or row.get("snippet") or "").strip()
        if title or snippet:
            results.append({"title": title, "url": url, "description": snippet})
        if len(results) >= 5:break
    return results

async def web_search(query: str) -> list[dict]:
    """依次尝试 Bing RSS、DuckDuckGo，先成功者返回。"""
    for searcher in (_bing_rss_search, _ddgs_search):
        try:
            hits = await asyncio.wait_for(
                asyncio.to_thread(searcher, query),
                timeout=60,
            )
        except Exception:  # noqa: BLE001 - 单路失败继续下一路
            continue
        if hits:
            return hits
    return []