"""Base class per tutti gli scraper"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class TorrentResult:
    source: str
    title: str
    magnet: str
    info_hash: str
    size_bytes: int
    seeders: int
    leechers: int
    quality: str
    audio_type: str  # "sub" | "dub" | "unknown"
    language: str
    group: str
    url: str
    episode: Optional[int] = None
    season: Optional[int] = None
    is_batch: bool = False
    has_ita_sub: Optional[bool] = None   # None = non verificato, True/False = verificato da debrid


def extract_quality(title: str) -> str:
    t = title.lower()
    if "2160p" in t or "4k" in t: return "4K"
    if "1080p" in t or "1080" in t: return "1080p"
    if "720p"  in t or "720"  in t: return "720p"
    if "480p"  in t or "480"  in t: return "480p"
    return "?"

def extract_audio_type(title: str) -> str:
    t = title.lower()
    for kw in ["dub ita","ita dub","dubbed","doppiato"]:
        if kw in t: return "dub"
    for kw in ["sub ita","ita sub","subbed","sottotitoli","sub-ita"]:
        if kw in t: return "sub"
    if "italiano" in t or "italian" in t or "[ita]" in t or "(ita)" in t:
        return "sub"
    return "unknown"

def extract_group(title: str) -> str:
    m = re.search(r'\[([A-Za-z0-9_\-\.]+)\]', title)
    return m.group(1) if m else "Unknown"

def extract_info_hash(magnet: str) -> str:
    m = re.search(r'urn:btih:([a-fA-F0-9]{40}|[A-Z2-7]{32})', magnet, re.IGNORECASE)
    if not m: return ""
    h = m.group(1)
    if len(h) == 32:
        import base64
        try: h = base64.b32decode(h.upper()).hex()
        except: pass
    return h.lower()

def has_ita_keywords(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in [
        "ita", "sub ita", "ita sub", "[ita]", "(ita)", "italiano", "italian",
        "dub ita", "ita dub", "doppiato", "sottotitoli", "sub-ita"
    ])


class BaseScraper(ABC):
    name: str = "base"

    def _build_search_query(self, title_en: str, title_it: str, episode: int) -> list[str]:
        queries = []
        ep = f"{episode:02d}"
        if title_en:
            queries.append(f"{title_en} {ep} ITA")
            queries.append(f"{title_en} {ep}")
        if title_it and title_it != title_en:
            queries.append(f"{title_it} {ep} ITA")
            queries.append(f"{title_it} {ep}")
        return queries

    @abstractmethod
    async def search(
        self,
        title_en: str,
        title_it: str,
        season: int,
        episode: int,
        **kwargs,
    ) -> list[TorrentResult]:
        pass
