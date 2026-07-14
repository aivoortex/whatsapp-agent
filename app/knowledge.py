import re
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models import KnowledgeDocument
from app.security import validate_public_http_url


class WebsiteImporter:
    def __init__(self, timeout: float, max_page_bytes: int):
        self.timeout = timeout
        self.max_page_bytes = max_page_bytes

    async def crawl(self, start_url: str, max_pages: int) -> list[KnowledgeDocument]:
        validate_public_http_url(start_url)
        origin = urlparse(start_url)
        queue, visited, documents = deque([start_url]), set(), []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, headers={"User-Agent": "WhatsAppAgentKnowledgeBot/0.1"}) as client:
            while queue and len(documents) < max_pages:
                url = urldefrag(queue.popleft()).url
                if url in visited:
                    continue
                visited.add(url)
                validate_public_http_url(url)
                try:
                    response = await client.get(url)
                    if response.is_redirect:
                        redirect = urljoin(url, response.headers.get("location", ""))
                        validate_public_http_url(redirect)
                        if urlparse(redirect).netloc == origin.netloc:
                            queue.appendleft(redirect)
                        continue
                    response.raise_for_status()
                except (httpx.HTTPError, ValueError):
                    continue
                final = urlparse(str(response.url))
                if final.netloc != origin.netloc or "text/html" not in response.headers.get("content-type", "").lower():
                    continue
                soup = BeautifulSoup(response.content[:self.max_page_bytes], "html.parser")
                for element in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
                    element.decompose()
                title = soup.title.get_text(" ", strip=True) if soup.title else str(response.url)
                text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
                if len(text) >= 80:
                    documents.append(KnowledgeDocument(url=str(response.url), title=title[:300], text=text[:50_000], fetched_at=datetime.now(UTC).isoformat()))
                for link in soup.select("a[href]"):
                    candidate = urldefrag(urljoin(str(response.url), link.get("href"))).url
                    parsed = urlparse(candidate)
                    if parsed.scheme in {"http", "https"} and parsed.netloc == origin.netloc and candidate not in visited:
                        queue.append(candidate)
        return documents


def retrieve(query: str, documents: list[dict], limit: int = 4):
    terms = set(re.findall(r"[\wÀ-ÿ]{3,}", query.lower()))
    scored = []
    for document in documents:
        haystack = f"{document['title']} {document['text']}".lower()
        matches = sum(min(haystack.count(term), 5) for term in terms)
        if matches:
            scored.append((document, round(matches / (len(terms) * 5), 3)))
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
