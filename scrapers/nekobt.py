"""
NekoBT scraper - tracker italiano per anime
"""

import asyncio
import logging
import urllib.parse
import re

import httpx

from scrapers.base import (
    BaseScraper, TorrentResult,
    extract_quality, extract_audio_type, extract_group, extract_info_hash
)

log = logging.getLogger(__name__)

ITA_KEYWORDS = [
    "sub ita", "ita sub", "[ita]", "(ita)", "italiano", "italian",
    "dub ita", "ita dub", "doppiato", "sottotitoli"
]


class NekoBTScraper(BaseScraper):
    name = "nekobt"

    async def search(self, title_en: str, title_it: str, season: int, episode: int, **kwargs) -> list[TorrentResult]:
        results = []
        titles_all = kwargs.get("titles_all") or []
        extra = [t for t in titles_all if t and t != title_en and t != title_it]
        all_en = title_en
        all_it = title_it
        if extra:
            title_en = extra[0] if not title_en else title_en
        queries = self._build_search_query(all_en or (extra[0] if extra else ""), all_it, episode)
        for t in extra:
            for q in self._build_search_query(t, "", episode):
                if q not in queries:
                    queries.append(q)

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, q) for q in queries[:2]]
            nested = await asyncio.gather(*tasks, return_exceptions=True)

        seen = set()
        for items in nested:
            if isinstance(items, Exception):
                log.warning(f"NekoBT error: {items}")
                continue
            for item in items:
                if item.info_hash not in seen:
                    seen.add(item.info_hash)
                    results.append(item)

        log.info(f"[NekoBT] {len(results)} risultati")
        return results

    async def _fetch(self, client: httpx.AsyncClient, query: str) -> list[TorrentResult]:
        encoded = urllib.parse.quote(query)
        url = f"https://www.nekobt.it/?search={encoded}&type=anime"

        try:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True,
                timeout=12,
            )
            resp.raise_for_status()
            return self._parse_html(resp.text)
        except Exception as e:
            log.debug(f"NekoBT fetch error: {e}")
            return []

    def _parse_html(self, html: str) -> list[TorrentResult]:
        results = []
        # Parsing semplice: cerca pattern comuni nei tracker italiani
        # I link magnet sono sempre riconoscibili
        magnets = re.findall(r'magnet:\?xt=urn:btih:[^"\'&\s<>]+', html)
        titles_raw = re.findall(r'class="[^"]*title[^"]*"[^>]*>([^<]+)<', html, re.IGNORECASE)

        for i, magnet in enumerate(magnets):
            ih = extract_info_hash(magnet)
            if not ih:
                continue

            title = titles_raw[i].strip() if i < len(titles_raw) else f"NekoBT result {i}"
            title_lower = title.lower()

            if not any(kw in title_lower for kw in ITA_KEYWORDS):
                # Potrebbe essere comunque ITA dato che è un tracker italiano
                # Includi comunque
                pass

            results.append(TorrentResult(
                source="nekobt",
                title=title,
                magnet=magnet,
                info_hash=ih,
                size_bytes=0,
                seeders=0,
                leechers=0,
                quality=extract_quality(title),
                audio_type=extract_audio_type(title),
                language="ita",
                group=extract_group(title),
                url="https://www.nekobt.it",
            ))

        return results
