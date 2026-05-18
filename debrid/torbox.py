"""
TorBox API client
Docs: https://api.torbox.app/
"""

import asyncio
import logging
import re
from typing import Optional

import httpx

from scrapers.base import TorrentResult
from debrid.realdebrid import DebridStream

log = logging.getLogger(__name__)

TB_BASE = "https://api.torbox.app/v1/api"

ITA_SUB_PATTERNS = re.compile(
    r'(sub[_\-\.]?ita|ita[_\-\.]?sub|italiano|italian|\.it\.|[_\-\[\(]ita[_\-\]\)])',
    re.IGNORECASE
)


def _file_has_ita_sub(name: str) -> bool:
    n = name.lower()
    is_sub = any(n.endswith(ext) for ext in ('.srt', '.ass', '.ssa', '.vtt', '.sub'))
    return is_sub and bool(ITA_SUB_PATTERNS.search(n))


def _files_have_ita_sub(files: list) -> bool:
    for f in files:
        name = f.get('name', '') or f.get('path', '') or ''
        if _file_has_ita_sub(name):
            return True
    return False


class TorBoxClient:
    name = "torbox"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def resolve_torrents(self, torrents: list[TorrentResult]) -> list[DebridStream]:
        if not torrents:
            return []

        info_hashes = [t.info_hash for t in torrents if t.info_hash]
        cached = await self._check_cache(info_hashes)

        cached_set = set(cached)
        sorted_torrents = sorted(
            [t for t in torrents if t.magnet],
            key=lambda x: (x.info_hash in cached_set, x.seeders),
            reverse=True,
        )[:5]

        streams = []
        async with httpx.AsyncClient(timeout=30) as client:
            for torrent in sorted_torrents:
                try:
                    stream = await self._resolve_single(client, torrent)
                    if stream:
                        streams.append(stream)
                except Exception as e:
                    log.warning(f"TorBox resolve error for {torrent.title[:50]}: {e}")

        return streams

    async def _check_cache(self, info_hashes: list[str]) -> list[str]:
        if not info_hashes:
            return []

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{TB_BASE}/torrents/checkcached",
                    params={"hash": ",".join(info_hashes[:50]), "format": "list"},
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("data", []) or []
                result = []
                for item in raw:
                    if isinstance(item, str):
                        result.append(item)
                    elif isinstance(item, dict):
                        h = item.get("hash", "") or item.get("info_hash", "")
                        if h:
                            result.append(h)
                return result
            except Exception as e:
                log.debug(f"TorBox cache check error: {e}")
                return []

    async def _resolve_single(
        self, client: httpx.AsyncClient, torrent: TorrentResult
    ) -> Optional[DebridStream]:
        # Step 1: crea torrent
        try:
            resp = await client.post(
                f"{TB_BASE}/torrents/createtorrent",
                json={
                    "magnet": torrent.magnet,
                    "seed": 1,
                    "allow_zip": False,
                },
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug(f"TorBox createtorrent error: {e}")
            return None

        torrent_id = data.get("data", {}).get("torrent_id") if isinstance(data.get("data"), dict) else None

        if not torrent_id:
            torrent_id = await self._find_existing(client, torrent.info_hash)

        if not torrent_id:
            return None

        # Step 2: aspetta che sia pronto
        torrent_info = None
        for _ in range(5):
            await asyncio.sleep(2)
            torrent_info = await self._get_torrent_info(client, torrent_id)
            if torrent_info and torrent_info.get("download_state") in ("completed", "cached", "seeding"):
                break

        # Controlla sub ITA nei file
        has_ita = False
        if torrent_info:
            files = torrent_info.get("files", []) or []
            has_ita = _files_have_ita_sub(files)
            log.debug(f"TorBox files ITA sub: {has_ita} for {torrent.title[:40]}")

        # Step 3: richiedi link
        try:
            resp = await client.get(
                f"{TB_BASE}/torrents/requestdl",
                params={
                    "token": self.api_key,
                    "torrent_id": torrent_id,
                    "file_id": "0",
                    "zip_link": False,
                },
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug(f"TorBox requestdl error: {e}")
            return None

        download_url = data.get("data", "")
        if not download_url:
            return None

        return DebridStream(
            url=download_url,
            filename=torrent.title,
            size_bytes=torrent.size_bytes,
            debrid="torbox",
            torrent=torrent,
            has_ita_sub=has_ita,
        )

    async def _find_existing(self, client: httpx.AsyncClient, info_hash: str) -> Optional[str]:
        try:
            resp = await client.get(
                f"{TB_BASE}/torrents/mylist",
                params={"bypass_cache": True},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", []) or []
            for item in items:
                if item.get("hash", "").lower() == info_hash.lower():
                    return str(item.get("id", ""))
        except Exception:
            pass
        return None

    async def _get_torrent_info(self, client: httpx.AsyncClient, torrent_id) -> Optional[dict]:
        try:
            resp = await client.get(
                f"{TB_BASE}/torrents/mylist",
                params={"id": torrent_id, "bypass_cache": True},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", []) or []
            return items[0] if items else None
        except Exception:
            return None
