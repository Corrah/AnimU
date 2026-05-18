"""
StreamFormatter - formatta i risultati per Stremio
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.base import TorrentResult
    from debrid.realdebrid import DebridStream


def _human_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def _quality_label(quality: str) -> str:
    map_ = {
        "4K":    "4K🔥",
        "2160p": "4K🔥",
        "1080p": "1080p🚀",
        "720p":  "720p💿",
        "480p":  "480p📺",
        "360p":  "360p",
        "?":     "?",
    }
    return map_.get(quality, quality)


def _source_label(source: str) -> str:
    map_ = {
        "nyaa":       "Nyaa",
        "animetosho": "AniTosho",
        "tokyotosho": "TkyTosho",
        "anidex":     "AniDex",
        "nekobt":     "NekoBT",
        "seadex":     "SeaDex",
    }
    return map_.get(source, source)


def _debrid_label(debrid: str) -> str:
    return "RD" if debrid == "realdebrid" else "TB"


class StreamFormatter:

    def format_streams(self, debrid_streams: list, original_torrents: list) -> list[dict]:
        streams = []
        for ds in debrid_streams:
            t = ds.torrent
            has_ita = ds.has_ita_sub or (t.audio_type in ("sub", "dub"))

            # Determina badge audio
            if t.audio_type == "dub":
                audio_badge = "🎙️ DUB ITA"
            elif t.audio_type == "sub" or ds.has_ita_sub:
                audio_badge = "📝 SUB ITA"
            else:
                audio_badge = "📝 SUB ?"

            debrid = _debrid_label(ds.debrid)
            quality = _quality_label(t.quality)
            source = _source_label(t.source)
            group = t.group if t.group and t.group != "Unknown" else ""
            size = _human_size(ds.size_bytes or t.size_bytes)

            # Nome (colonna sinistra)
            name = f"{quality}\n[{debrid}⚡☁️]\n[AnimU]\n{audio_badge}"

            # Descrizione (colonna destra)
            desc_parts = []
            if size:
                desc_parts.append(f"📦 {size}")
            if group:
                desc_parts.append(f"🏷️ {group}")
            desc_parts.append(f"🌐 {source}")
            if ds.has_ita_sub:
                desc_parts.append("✅ Sub ITA verificati")

            filename = ds.filename or t.title
            if filename:
                desc_parts.append(f"📄 {filename[:80]}")

            desc = "\n".join(desc_parts)

            streams.append({
                "url": ds.url,
                "name": name,
                "title": desc,
                "behaviorHints": {
                    "notWebReady": False,
                    "bingeGroup": f"animu-{t.source}-{t.audio_type}-{t.quality}",
                },
            })
        return streams

    def format_magnet_streams(self, torrents: list) -> list[dict]:
        streams = []
        for t in sorted(torrents, key=lambda x: x.seeders, reverse=True)[:10]:
            if not t.magnet:
                continue

            if t.audio_type == "dub":
                audio_badge = "🎙️ DUB ITA"
            elif t.audio_type == "sub":
                audio_badge = "📝 SUB ITA"
            else:
                audio_badge = "📝 SUB ?"

            quality = _quality_label(t.quality)
            source = _source_label(t.source)
            group = t.group if t.group and t.group != "Unknown" else ""
            size = _human_size(t.size_bytes)

            name = f"{quality}\n⚠️ P2P\n[AnimU]\n{audio_badge}"

            desc_parts = []
            if size:
                desc_parts.append(f"📦 {size}")
            if group:
                desc_parts.append(f"🏷️ {group}")
            desc_parts.append(f"🌐 {source}")
            desc_parts.append(f"📄 {t.title[:80]}")

            streams.append({
                "infoHash": t.info_hash,
                "name": name,
                "title": "\n".join(desc_parts),
                "sources": [t.magnet],
            })
        return streams
