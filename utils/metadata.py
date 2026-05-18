"""
Metadata resolver
Estrae da Kitsu: titolo EN, titolo JP (romaji), titolo IT, MAL ID, stagione, episodio
Tutti i titoli alternativi vengono usati dagli scraper per massimizzare il match
"""

import logging
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class MetadataResolver:

    async def resolve(self, media_type: str, stremio_id: str) -> dict:
        result = {
            "title_en":    "",
            "title_jp":    "",   # romaji — es. "Tongari Boushi no Atelier"
            "title_it":    "",
            "titles_all":  [],   # tutti i titoli alternativi
            "mal_id":      None,
            "season":      1,
            "episode":     1,
            "year":        0,
            "is_movie":    media_type == "movie",
        }

        parts = stremio_id.split(":")

        if stremio_id.startswith("kitsu:"):
            kitsu_id = parts[1]
            if len(parts) == 3:
                result["season"]  = 1
                result["episode"] = int(parts[2])
            elif len(parts) >= 4:
                result["season"]  = int(parts[2])
                result["episode"] = int(parts[3])
            meta = await self._resolve_kitsu(kitsu_id)
            result.update(meta)

        elif stremio_id.startswith("tt"):
            imdb_id = parts[0]
            if len(parts) >= 3:
                result["season"]  = int(parts[1])
                result["episode"] = int(parts[2])
            meta = await self._resolve_imdb(imdb_id)
            result.update(meta)

        elif stremio_id.startswith("tmdb:"):
            tmdb_id = parts[1]
            if len(parts) >= 4:
                result["season"]  = int(parts[2])
                result["episode"] = int(parts[3])
            meta = await self._resolve_tmdb(tmdb_id)
            result.update(meta)

        # Costruisce lista deduplicata di tutti i titoli
        seen = set()
        all_titles = []
        for t in [result["title_en"], result["title_jp"], result["title_it"]]:
            if t and t.lower() not in seen:
                seen.add(t.lower())
                all_titles.append(t)
        result["titles_all"] = all_titles

        log.info(f"Metadata finale: titles={all_titles} mal_id={result['mal_id']} S{result['season']}E{result['episode']}")
        return result

    async def _resolve_kitsu(self, kitsu_id: str) -> dict:
        url = f"https://kitsu.io/api/edge/anime/{kitsu_id}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Accept":     "application/vnd.api+json",
                        "User-Agent": "AnimU-Stremio-Addon/1.0",
                    }
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log.warning(f"Kitsu API error for {kitsu_id}: {e}")
            return {}

        attrs  = data.get("data", {}).get("attributes", {})
        titles = attrs.get("titles", {})

        # en_jp = romaji (es. "Tongari Boushi no Atelier") — FONDAMENTALE per i tracker
        title_jp = titles.get("en_jp") or titles.get("ja_jp") or ""
        title_en = (
            titles.get("en_us") or
            titles.get("en")    or
            attrs.get("canonicalTitle") or
            title_jp or ""
        )
        title_it = titles.get("it") or ""

        # MAL ID dalla relazione mappings
        mal_id = None
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"https://kitsu.io/api/edge/anime/{kitsu_id}/mappings",
                    headers={"Accept": "application/vnd.api+json", "User-Agent": "AnimU/1.0"},
                )
                r.raise_for_status()
                mappings = r.json().get("data", [])
                for m in mappings:
                    ext = m.get("attributes", {}).get("externalSite", "")
                    if ext == "myanimelist/anime":
                        mal_id = int(m["attributes"]["externalId"])
                        break
        except Exception as e:
            log.debug(f"Kitsu mappings error: {e}")

        year = 0
        started = attrs.get("startDate", "") or ""
        if started:
            try:
                year = int(started[:4])
            except Exception:
                pass

        log.info(f"Kitsu {kitsu_id} → EN='{title_en}' JP='{title_jp}' IT='{title_it}' MAL={mal_id}")
        return {
            "title_en": title_en,
            "title_jp": title_jp,
            "title_it": title_it,
            "mal_id":   mal_id,
            "year":     year,
        }

    async def _resolve_imdb(self, imdb_id: str) -> dict:
        tmdb_key = "1f54bd990f1cdfb230adb312546d765d"
        url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={tmdb_key}&external_source=imdb_id"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            results = data.get("tv_results", []) or data.get("movie_results", [])
            if results:
                item = results[0]
                return {"title_en": item.get("name") or item.get("title") or ""}
        except Exception as e:
            log.warning(f"IMDB resolve error: {e}")
        return {}

    async def _resolve_tmdb(self, tmdb_id: str) -> dict:
        tmdb_key = "1f54bd990f1cdfb230adb312546d765d"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r_it = await client.get(
                    f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={tmdb_key}&language=it-IT"
                )
                r_en = await client.get(
                    f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={tmdb_key}&language=en-US"
                )
            return {
                "title_it": r_it.json().get("name") or "",
                "title_en": r_en.json().get("name") or "",
            }
        except Exception as e:
            log.warning(f"TMDB resolve error: {e}")
        return {}
