"""
Real-Debrid API client
Docs: https://api.real-debrid.com/
"""

import asyncio
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

import httpx

from scrapers.base import TorrentResult

log = logging.getLogger(__name__)

RD_BASE = "https://api.real-debrid.com/rest/1.0"

ITA_SUB_PATTERNS = re.compile(
    r'(sub[_\-\.]?ita|ita[_\-\.]?sub|italiano|italian|\.it\.|[_\-\[\(]ita[_\-\]\)])',
    re.IGNORECASE
)


@dataclass
class DebridStream:
    url: str
    filename: str
    size_bytes: int
    debrid: str          # "realdebrid" | "torbox"
    torrent: TorrentResult
    has_ita_sub: bool = False   # rilevato dai file del torrent


def _file_has_ita_sub(path: str) -> bool:
    """Controlla se un file subtitle ha ITA nel nome"""
    p = path.lower()
    is_sub = any(p.endswith(ext) for ext in ('.srt', '.ass', '.ssa', '.vtt', '.sub'))
    return is_sub and bool(ITA_SUB_PATTERNS.search(p))


def _files_have_ita_sub(files: list[dict]) -> bool:
    """Controlla se la lista file contiene almeno un subtitle ITA"""
    return any(_file_has_ita_sub(f.get('path', '')) for f in files)


class RealDebridClient:
    name = "realdebrid"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def resolve_torrents(self, torrents: list[TorrentResult]) -> list[DebridStream]:
        if not torrents:
            return []

        sorted_torrents = sorted(
            [t for t in torrents if t.magnet],
            key=lambda x: x.seeders,
            reverse=True
        )[:5]

        streams = []
        async with httpx.AsyncClient(timeout=30) as client:
            for torrent in sorted_torrents:
                try:
                    stream = await self._resolve_single(client, torrent)
                    if stream:
                        streams.append(stream)
                except Exception as e:
                    log.warning(f"RD resolve error for {torrent.title[:50]}: {e}")

        return streams

    async def _resolve_single(
        self, client: httpx.AsyncClient, torrent: TorrentResult
    ) -> Optional[DebridStream]:
        # Step 1: aggiungi magnet
        try:
            resp = await client.post(
                f"{RD_BASE}/torrents/addMagnet",
                data={"magnet": torrent.magnet},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug(f"RD addMagnet error: {e}")
            return None

        torrent_id = data.get("id")
        if not torrent_id:
            return None

        # Step 2: ottieni info per vedere i file
        await asyncio.sleep(2)
        try:
            resp = await client.get(
                f"{RD_BASE}/torrents/info/{torrent_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            info = resp.json()
        except Exception as e:
            log.debug(f"RD info error: {e}")
            return None

        status = info.get("status", "")
        all_files = info.get("files", [])

        # Controlla subtitle ITA tra i file
        has_ita = _files_have_ita_sub(all_files)
        log.debug(f"RD files ITA sub: {has_ita} for {torrent.title[:40]}")

        if status in ("magnet_done", "waiting_files_selection"):
            # Seleziona file video
            video_ids = [
                str(f["id"]) for f in all_files
                if any(f.get("path", "").lower().endswith(ext)
                       for ext in (".mkv", ".mp4", ".avi"))
            ]
            if not video_ids:
                video_ids = ["all"]

            try:
                await client.post(
                    f"{RD_BASE}/torrents/selectFiles/{torrent_id}",
                    data={"files": ",".join(video_ids)},
                    headers=self._headers,
                )
            except Exception:
                pass

            await asyncio.sleep(1)

        # Step 3: ottieni i link
        try:
            resp = await client.get(
                f"{RD_BASE}/torrents/info/{torrent_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            info = resp.json()
        except Exception:
            return None

        links = info.get("links", [])
        if not links:
            return None

        # Step 4: unrestrict
        for link in links:
            try:
                resp = await client.post(
                    f"{RD_BASE}/unrestrict/link",
                    data={"link": link},
                    headers=self._headers,
                )
                resp.raise_for_status()
                unrestricted = resp.json()

                final_url = unrestricted.get("download", "")
                filename = unrestricted.get("filename", torrent.title)
                size = unrestricted.get("filesize", torrent.size_bytes)

                if final_url:
                    return DebridStream(
                        url=final_url,
                        filename=filename,
                        size_bytes=size,
                        debrid="realdebrid",
                        torrent=torrent,
                        has_ita_sub=has_ita,
                    )
            except Exception as e:
                log.debug(f"RD unrestrict error: {e}")
                continue

        return None

    async def check_availability(self, info_hashes: list[str]) -> dict:
        if not info_hashes:
            return {}
        hashes_str = "/".join(info_hashes[:100])
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{RD_BASE}/torrents/instantAvailability/{hashes_str}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                log.debug(f"RD availability check error: {e}")
                return {}
