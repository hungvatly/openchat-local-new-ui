"""
OpenChat Local — Web Search
Supports SearXNG (self-hosted) or DuckDuckGo HTML fallback.
"""
import re
import json
from typing import List, Dict, Optional
import aiohttp
from bs4 import BeautifulSoup

from config import settings


class WebSearchEngine:
    """Web search via SearXNG (preferred) or DuckDuckGo Lite (fallback)."""

    def __init__(self):
        self.searxng_url = getattr(settings, "SEARXNG_URL", "")
        self.timeout = aiohttp.ClientTimeout(total=15)

    async def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search the web and return results."""
        if self.searxng_url:
            results = await self._search_searxng(query, max_results)
            if results:
                return results

        return await self._search_duckduckgo(query, max_results)

    async def _search_searxng(self, query: str, max_results: int) -> List[Dict]:
        """Search using a SearXNG instance (JSON API)."""
        try:
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "en",
                "pageno": 1,
            }
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.searxng_url}/search",
                    params=params,
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    results = []
                    for item in data.get("results", [])[:max_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("content", ""),
                            "source": "searxng",
                        })
                    return results
        except Exception as e:
            print(f"SearXNG error: {e}")
            return []

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        """Fallback: search DuckDuckGo Lite (no API key needed)."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; OpenChatLocal/1.0)"
            }
            params = {"q": query}
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    "https://lite.duckduckgo.com/lite",
                    params=params,
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        return []
                    html = await resp.text()
                    return self._parse_ddg_lite(html, max_results)
        except Exception as e:
            print(f"DuckDuckGo error: {e}")
            return []

    def _parse_ddg_lite(self, html: str, max_results: int) -> List[Dict]:
        """Parse DuckDuckGo Lite HTML results."""
        soup = BeautifulSoup(html, "html.parser")
        results = []
        links = soup.find_all("a", class_="result-link")

        if not links:
            rows = soup.find_all("tr")
            for row in rows:
                link = row.find("a", href=True)
                snippet_td = row.find("td", class_="result-snippet")
                if link and link.get("href", "").startswith("http"):
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": link["href"],
                        "snippet": snippet_td.get_text(strip=True) if snippet_td else "",
                        "source": "duckduckgo",
                    })
                    if len(results) >= max_results:
                        break
        else:
            for link in links[:max_results]:
                parent = link.find_parent("tr")
                snippet = ""
                if parent:
                    next_row = parent.find_next_sibling("tr")
                    if next_row:
                        snippet = next_row.get_text(strip=True)
                results.append({
                    "title": link.get_text(strip=True),
                    "url": link["href"],
                    "snippet": snippet,
                    "source": "duckduckgo",
                })

        return results

    async def fetch_page(self, url: str, max_chars: int = 3000) -> Optional[str]:
        """Fetch and extract text content from a URL."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; OpenChatLocal/1.0)"
            }
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    content_type = resp.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        return None
                    html = await resp.text()
                    return self._extract_text(html, max_chars)
        except Exception as e:
            print(f"Fetch error for {url}: {e}")
            return None

    def _extract_text(self, html: str, max_chars: int) -> str:
        """Extract readable text from HTML."""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        article = soup.find("article") or soup.find("main") or soup.find("body")
        if not article:
            return ""

        text = article.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 20]
        clean_text = "\n".join(lines)

        return clean_text[:max_chars]


web_search = WebSearchEngine()
