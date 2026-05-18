"""
TokyoTosho scraper - usa RSS
"""

import asyncio
import logging
import urllib.parse
import xml.etree.ElementTree as ET

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


class TokyoToshoScraper(BaseScraper):
    name = "tokyotosho"

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
            tasks = [self._fetch_rss(client, q) for q in queries[:2]]
            nested = await asyncio.gather(*tasks, return_exceptions=True)

        seen_hashes = set()
        for items in nested:
            if isinstance(items, Exception):
                log.warning(f"TokyoTosho error: {items}")
                continue
            for item in items:
                if item.info_hash and item.info_hash not in seen_hashes:
                    seen_hashes.add(item.info_hash)
                    results.append(item)

        log.info(f"[TokyoTosho] {len(results)} risultati")
        return results

    async def _fetch_rss(self, client: httpx.AsyncClient, query: str) -> list[TorrentResult]:
        encoded = urllib.parse.quote(query)
        url = f"https://www.tokyotosho.info/rss.php?terms={encoded}&type=1"

        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            log.debug(f"TokyoTosho fetch error ({query}): {e}")
            return []

        return self._parse_rss(resp.text)

    def _parse_rss(self, xml_text: str) -> list[TorrentResult]:
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title = item.findtext("title", "").strip()
            title_lower = title.lower()

            # Nessun filtro ITA - verifica fatta da debrid

            link = item.findtext("link", "").strip()
            # TokyoTosho non ha magnet direttamente nel RSS
            # Proviamo a trovarlo nella description
            desc = item.findtext("description", "") or ""

            # Cerca il link .torrent
            torrent_url = ""
            import re
            m = re.search(r'href=["\']([^"\']+\.torrent[^"\']*)["\']', desc, re.IGNORECASE)
            if m:
                torrent_url = m.group(1)

            # Cerca info_hash se disponibile
            m_hash = re.search(r'([a-fA-F0-9]{40})', desc + link)
            info_hash = m_hash.group(1).lower() if m_hash else ""

            if not info_hash and not torrent_url:
                continue

            magnet = ""
            if info_hash:
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(title)}"
            
            # Size parsing
            size_bytes = 0
            m_size = re.search(r'Size:\s*([\d\.]+)\s*(MiB|GiB|MB|GB)', desc, re.IGNORECASE)
            if m_size:
                val = float(m_size.group(1))
                unit = m_size.group(2).upper()
                mult = {"MIB": 1024**2, "GIB": 1024**3, "MB": 1000**2, "GB": 1000**3}
                size_bytes = int(val * mult.get(unit, 1))

            results.append(TorrentResult(
                source="tokyotosho",
                title=title,
                magnet=magnet,
                info_hash=info_hash,
                size_bytes=size_bytes,
                seeders=0,
                leechers=0,
                quality=extract_quality(title),
                audio_type=extract_audio_type(title),
                language="ita",
                group=extract_group(title),
                url=link,
            ))

        return results
