"""
Nyaa.si scraper - cerca tutti i torrent senza filtro ITA
"""

import asyncio
import logging
import urllib.parse
import xml.etree.ElementTree as ET

import httpx

from scrapers.base import (
    BaseScraper, TorrentResult,
    extract_quality, extract_audio_type, extract_group, extract_info_hash,
    has_ita_keywords,
)

log = logging.getLogger(__name__)


class NyaaScraper(BaseScraper):
    name = "nyaa"

    async def search(self, title_en, title_it, season, episode, **kwargs) -> list[TorrentResult]:
        titles_all = kwargs.get("titles_all") or []
        if not titles_all:
            titles_all = [t for t in [title_en, title_it] if t]

        ep_str = f"{episode:02d}"

        queries = []
        for title in titles_all:
            if not title:
                continue
            # Con ITA esplicito
            queries.append((f"{title} {ep_str} ITA", "1_4"))
            queries.append((f"{title} {ep_str} ITA", "0_0"))
            # Senza ITA (per release con sub inclusi ma non nel titolo)
            queries.append((f"{title} {ep_str}", "1_4"))
            queries.append((f"{title} {ep_str}", "0_0"))

        seen_q = set()
        unique_queries = []
        for q, cat in queries:
            key = q.lower() + cat
            if key not in seen_q:
                seen_q.add(key)
                unique_queries.append((q, cat))

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch_rss(client, q, cat) for q, cat in unique_queries[:10]]
            nested = await asyncio.gather(*tasks, return_exceptions=True)

        seen_hashes = set()
        results = []
        for items in nested:
            if isinstance(items, Exception):
                continue
            for item in items:
                if item.info_hash and item.info_hash not in seen_hashes:
                    seen_hashes.add(item.info_hash)
                    results.append(item)

        log.info(f"[Nyaa] {len(results)} risultati unici")
        return results

    async def _fetch_rss(self, client, query: str, category: str = "1_4") -> list[TorrentResult]:
        encoded = urllib.parse.quote(query)
        url = f"https://nyaa.si/?page=rss&c={category}&f=0&q={encoded}"
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            resp.raise_for_status()
        except Exception as e:
            log.debug(f"Nyaa RSS error ({query}): {e}")
            return []
        return self._parse_rss(resp.text)

    def _parse_rss(self, xml_text: str) -> list[TorrentResult]:
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        ns = {"nyaa": "https://nyaa.si/xmlns/nyaa"}
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title = item.findtext("title", "").strip()

            magnet_el = item.find("nyaa:magnetUri", ns)
            magnet = magnet_el.text or "" if magnet_el is not None else ""
            if not magnet:
                continue

            info_hash = extract_info_hash(magnet)
            size_str = (item.find("nyaa:size", ns) or type('', (), {'text': ''})()).text or ""
            size_bytes = _parse_size(size_str)

            seeders = leechers = 0
            try: seeders  = int((item.find("nyaa:seeders",  ns) or type('', (), {'text': '0'})()).text or 0)
            except: pass
            try: leechers = int((item.find("nyaa:leechers", ns) or type('', (), {'text': '0'})()).text or 0)
            except: pass

            audio = extract_audio_type(title)
            lang = "ita" if has_ita_keywords(title) else "unknown"

            results.append(TorrentResult(
                source="nyaa", title=title, magnet=magnet, info_hash=info_hash,
                size_bytes=size_bytes, seeders=seeders, leechers=leechers,
                quality=extract_quality(title), audio_type=audio,
                language=lang, group=extract_group(title),
                url=item.findtext("link", ""),
            ))
        return results


def _parse_size(size_str: str) -> int:
    size_str = size_str.strip()
    try:
        parts = size_str.split()
        if len(parts) < 2:
            return 0
        value = float(parts[0])
        unit  = parts[1].upper()
        mult  = {"B":1,"KIB":1024,"MIB":1024**2,"GIB":1024**3,"KB":1000,"MB":1000**2,"GB":1000**3}
        return int(value * mult.get(unit, 1))
    except Exception:
        return 0
