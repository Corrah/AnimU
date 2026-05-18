"""
AnimeTosho scraper
Cerca tutti i torrent (senza filtro ITA nel titolo).
Il controllo ITA viene fatto da debrid sui file interni.
"""

import asyncio
import logging
import urllib.parse

import httpx

from scrapers.base import (
    BaseScraper, TorrentResult,
    extract_quality, extract_audio_type, extract_group, extract_info_hash,
    has_ita_keywords,
)

log = logging.getLogger(__name__)


class AnimeToshoScraper(BaseScraper):
    name = "animetosho"

    async def search(self, title_en, title_it, season, episode, **kwargs) -> list[TorrentResult]:
        mal_id     = kwargs.get("mal_id")
        titles_all = kwargs.get("titles_all") or [title_en, title_it]
        ep_str     = f"{episode:02d}"

        results = []
        seen = set()

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = []

            if mal_id:
                tasks.append(self._fetch_by_id(client, mal_id, episode))

            for title in titles_all:
                if not title:
                    continue
                tasks.append(self._fetch_by_query(client, f"{title} {ep_str}"))
                tasks.append(self._fetch_by_query(client, f"{title} {ep_str} ITA"))

            nested = await asyncio.gather(*tasks, return_exceptions=True)

        for items in nested:
            if isinstance(items, Exception):
                log.debug(f"AnimeTosho task error: {items}")
                continue
            for item in items:
                if item.info_hash and item.info_hash not in seen:
                    seen.add(item.info_hash)
                    results.append(item)

        log.info(f"[AnimeTosho] {len(results)} risultati unici")
        return results

    async def _fetch_by_id(self, client, mal_id: int, episode: int) -> list[TorrentResult]:
        url = f"https://feed.animetosho.org/json?mal={mal_id}&limit=100"
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug(f"AnimeTosho by_id error: {e}")
            return []

        if not isinstance(data, list):
            return []

        results = []
        ep_patterns = [
            f" {episode:02d} ", f" {episode:02d}v",
            f"E{episode:02d}", f"e{episode:02d}",
            f" - {episode:02d}", f"_{episode:02d}_", f"[{episode:02d}]",
            f"S{episode:02d}E", f"s{episode:02d}e",
        ]

        for item in data:
            title = item.get("title", "") or ""
            if not any(p in title for p in ep_patterns):
                is_batch = any(w in title.lower() for w in ["batch", "complete", "01-", "pack"])
                if not is_batch:
                    continue
            result = self._item_to_result(item, title)
            if result:
                results.append(result)

        return results

    async def _fetch_by_query(self, client, query: str) -> list[TorrentResult]:
        encoded = urllib.parse.quote(query)
        url = f"https://feed.animetosho.org/json?q={encoded}&limit=30"
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug(f"AnimeTosho query error ({query}): {e}")
            return []

        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            title = item.get("title", "") or ""
            result = self._item_to_result(item, title)
            if result:
                results.append(result)
        return results

    def _item_to_result(self, item: dict, title: str) -> TorrentResult | None:
        magnet = item.get("magnet_uri", "") or ""
        ih     = item.get("info_hash", "") or ""
        if not magnet and ih:
            import urllib.parse as up
            magnet = f"magnet:?xt=urn:btih:{ih}&dn={up.quote(title)}"
        if not magnet:
            return None
        info_hash = ih.lower() if ih else extract_info_hash(magnet)

        # Determina audio_type dal titolo
        audio = extract_audio_type(title)
        # Se ha keywords ITA nel titolo ma non riconosciuto come sub/dub, forza sub
        if audio == "unknown" and has_ita_keywords(title):
            audio = "sub"

        return TorrentResult(
            source="animetosho",
            title=title,
            magnet=magnet,
            info_hash=info_hash,
            size_bytes=item.get("total_size", 0) or 0,
            seeders=item.get("seeders", 0) or 0,
            leechers=item.get("leechers", 0) or 0,
            quality=extract_quality(title),
            audio_type=audio,
            language="ita" if has_ita_keywords(title) else "unknown",
            group=extract_group(title),
            url=item.get("link", ""),
        )
