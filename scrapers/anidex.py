"""
AniDex scraper - usa l'API JSON
"""

import asyncio
import logging
import urllib.parse

import httpx

from scrapers.base import (
    BaseScraper, TorrentResult,
    extract_quality, extract_audio_type, extract_group, extract_info_hash
)

log = logging.getLogger(__name__)

# AniDex API
ANIDEX_API = "https://anidex.info/api/?q={query}&lang_id=14"
# lang_id=14 = Italian

ITA_KEYWORDS = [
    "sub ita", "ita sub", "[ita]", "(ita)", "italiano", "italian",
    "dub ita", "ita dub", "doppiato", "sottotitoli"
]


class AniDexScraper(BaseScraper):
    name = "anidex"

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

        seen_hashes = set()
        for items in nested:
            if isinstance(items, Exception):
                log.warning(f"AniDex error: {items}")
                continue
            for item in items:
                if item.info_hash and item.info_hash not in seen_hashes:
                    seen_hashes.add(item.info_hash)
                    results.append(item)

        log.info(f"[AniDex] {len(results)} risultati")
        return results

    async def _fetch(self, client: httpx.AsyncClient, query: str) -> list[TorrentResult]:
        encoded = urllib.parse.quote(query)
        # Prova prima con filtro italiano, poi senza
        urls = [
            f"https://anidex.info/api/?q={encoded}&lang_id=14",
            f"https://anidex.info/api/?q={encoded}",
        ]

        for url in urls:
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                items = self._parse(data)
                if items:
                    return items
            except Exception as e:
                log.debug(f"AniDex fetch error ({url}): {e}")
                continue

        return []

    def _parse(self, data) -> list[TorrentResult]:
        results = []

        # AniDex API può restituire una lista o un dict con chiave "data"
        if isinstance(data, dict):
            items = data.get("data", []) or []
        elif isinstance(data, list):
            items = data
        else:
            return []

        for item in items:
            if not isinstance(item, dict):
                continue

            title = item.get("torrent_name", item.get("title", "")) or ""
            title_lower = title.lower()

            # Controlla lingua dal campo o dal titolo
            lang = str(item.get("lang_id", item.get("language", "")) or "")
            is_ita = (lang in ("14", "it", "ita") or
                      any(kw in title_lower for kw in ITA_KEYWORDS))

            if not is_ita:
                continue

            torrent_id = item.get("id", "") or ""
            info_hash = str(item.get("info_hash", "") or "").lower()
            magnet = item.get("magnet", "") or ""

            if not magnet and info_hash:
                import urllib.parse as up
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={up.quote(title)}"

            if not magnet:
                continue

            if not info_hash:
                info_hash = extract_info_hash(magnet)

            size_bytes = int(item.get("file_size", 0) or 0)
            seeders = int(item.get("seeders", 0) or 0)
            leechers = int(item.get("leechers", 0) or 0)

            url = f"https://anidex.info/torrent/{torrent_id}" if torrent_id else ""

            results.append(TorrentResult(
                source="anidex",
                title=title,
                magnet=magnet,
                info_hash=info_hash,
                size_bytes=size_bytes,
                seeders=seeders,
                leechers=leechers,
                quality=extract_quality(title),
                audio_type=extract_audio_type(title),
                language="ita",
                group=extract_group(title),
                url=url,
            ))

        return results
