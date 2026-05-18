"""
SeaDex scraper
SeaDex è una lista curata delle migliori release per ogni anime.
Ha un'API JSON pubblica: https://releases.moe
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

SEADEX_API = "https://releases.moe/api/collections/entries/records"

ITA_KEYWORDS = [
    "sub ita", "ita sub", "[ita]", "(ita)", "italiano", "italian",
    "dub ita", "ita dub", "doppiato"
]


class SeaDexScraper(BaseScraper):
    name = "seadex"

    async def search(self, title_en: str, title_it: str, season: int, episode: int, **kwargs) -> list[TorrentResult]:
        """
        SeaDex è una lista curata di release di qualità.
        Cerca il titolo e poi filtra per ITA se possibile.
        Nota: SeaDex è principalmente EN, le release ITA sono rare.
        """
        if not title_en:
            return []

        try:
            torrents = await self._search_seadex(title_en, episode)
            log.info(f"[SeaDex] {len(torrents)} risultati")
            return torrents
        except Exception as e:
            log.warning(f"SeaDex error: {e}")
            return []

    async def _search_seadex(self, title: str, episode: int) -> list[TorrentResult]:
        # SeaDex API usa PocketBase
        filter_str = f'(title~"{title}")'
        params = {
            "filter": filter_str,
            "perPage": 20,
            "expand": "trs",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    SEADEX_API,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.debug(f"SeaDex API error: {e}")
                return []

        results = []
        items = data.get("items", []) if isinstance(data, dict) else []

        for item in items:
            # Gli entries di SeaDex hanno "trs" (tracker entries) espansi
            expand = item.get("expand", {}) or {}
            trs = expand.get("trs", []) or []

            for tr in trs:
                if not isinstance(tr, dict):
                    continue

                # Controlla se è ITA
                notes = str(tr.get("notes", "") or "").lower()
                url = str(tr.get("url", "") or "")
                title_tr = str(tr.get("title", item.get("title", "")) or "")

                is_ita = any(kw in notes for kw in ITA_KEYWORDS) or \
                         any(kw in title_tr.lower() for kw in ITA_KEYWORDS)

                if not is_ita:
                    continue

                # Estrai info_hash/magnet dall'URL
                info_hash = ""
                magnet = ""

                if "nyaa.si" in url:
                    # Prova a ricavare info_hash dalla pagina nyaa
                    m = __import__("re").search(r'/view/(\d+)', url)
                    if m:
                        magnet = f"magnet:?xt=urn:btih:PLACEHOLDER&dn={urllib.parse.quote(title_tr)}"
                elif url.startswith("magnet:"):
                    magnet = url
                    info_hash = extract_info_hash(magnet)

                if not magnet:
                    continue

                results.append(TorrentResult(
                    source="seadex",
                    title=title_tr or item.get("title", ""),
                    magnet=magnet,
                    info_hash=info_hash,
                    size_bytes=0,
                    seeders=0,
                    leechers=0,
                    quality=extract_quality(title_tr),
                    audio_type=extract_audio_type(title_tr),
                    language="ita",
                    group=extract_group(title_tr),
                    url=url,
                ))

        return results
