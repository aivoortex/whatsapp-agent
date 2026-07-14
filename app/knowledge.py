import math
import re
import unicodedata
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models import KnowledgeDocument
from app.security import UnsafeUrlError, validate_public_http_url

STOP_WORDS = {
    "para", "como", "com", "uma", "que", "dos", "das", "por", "qual", "quais",
    "the", "and", "for", "you", "your", "con", "los", "las", "del", "como",
}


@dataclass
class RankedDocument:
    document: dict
    score: float
    excerpt: str


class WebsiteImporter:
    def __init__(self, timeout: float, max_page_bytes: int):
        self.timeout = timeout
        self.max_page_bytes = max_page_bytes

    async def crawl(self, start_url: str, max_pages: int) -> list[KnowledgeDocument]:
        validate_public_http_url(start_url)
        origin = urlparse(start_url)
        queue, visited, documents = deque([start_url]), set(), []
        headers = {"User-Agent": "WhatsAppAgentKnowledgeBot/0.2 (+knowledge-sync)"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, headers=headers) as client:
            while queue and len(documents) < max_pages:
                url = urldefrag(queue.popleft()).url
                if url in visited:
                    continue
                visited.add(url)
                try:
                    validate_public_http_url(url)
                    response = await client.get(url)
                    if response.is_redirect:
                        redirect = urljoin(url, response.headers.get("location", ""))
                        validate_public_http_url(redirect)
                        if urlparse(redirect).netloc == origin.netloc:
                            queue.appendleft(redirect)
                        continue
                    response.raise_for_status()
                except (httpx.HTTPError, UnsafeUrlError, ValueError):
                    continue
                if urlparse(str(response.url)).netloc != origin.netloc:
                    continue
                if "text/html" not in response.headers.get("content-type", "").lower():
                    continue
                try:
                    declared_size = int(response.headers.get("content-length", "0") or 0)
                except ValueError:
                    declared_size = 0
                if declared_size > self.max_page_bytes:
                    continue
                soup = BeautifulSoup(response.content[: self.max_page_bytes], "html.parser")
                for element in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
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


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{3,}", normalize(value)) if token not in STOP_WORDS]


def retrieve(query: str, documents: list[dict], limit: int = 4) -> list[RankedDocument]:
    query_terms = tokenize(query)
    if not query_terms or not documents:
        return []
    document_terms = [tokenize(f"{doc['title']} {doc['text']}") for doc in documents]
    frequencies = Counter(term for terms in document_terms for term in set(terms))
    total = len(documents)
    ranked = []
    for document, terms in zip(documents, document_terms):
        counts, length = Counter(terms), max(len(terms), 1)
        title_terms = set(tokenize(document["title"]))
        score = 0.0
        for term in set(query_terms):
            tf = counts[term] / length
            idf = math.log((total + 1) / (frequencies[term] + 0.5)) + 1
            score += tf * idf * 12
            if term in title_terms:
                score += 0.12
        phrase = normalize(query).strip()
        if len(phrase) > 5 and phrase in normalize(document["text"]):
            score += 0.25
        score = min(round(score, 3), 1.0)
        if score > 0:
            ranked.append(RankedDocument(document, score, best_excerpt(document["text"], query_terms)))
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


def best_excerpt(text: str, query_terms: list[str], max_chars: int = 700) -> str:
    normalized = normalize(text)
    positions = [normalized.find(term) for term in query_terms if normalized.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - 140)
    end = min(len(text), start + max_chars)
    excerpt = text[start:end]
    if start:
        excerpt = excerpt.split(" ", 1)[-1]
    if end < len(text):
        excerpt = excerpt.rsplit(" ", 1)[0]
    return excerpt.strip()
