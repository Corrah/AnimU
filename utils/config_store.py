"""
ConfigStore - salva e legge la configurazione dell'addon su disco
Il file config.json viene scritto dalla pagina /configure
e letto da ogni richiesta /stream
"""

import json
import os
import logging

log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
CONFIG_PATH = os.path.abspath(CONFIG_PATH)

DEFAULT_CONFIG = {
    "rd": "",
    "tb": "",
    "audio": "both",
    "minQ": 720,
    "sort": "quality",
    "sources": ["nyaa", "animetosho", "tokyotosho", "anidex", "nekobt", "seadex"],
}


def load() -> dict:
    """Legge config.json, fallback ai valori default"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                # merge con default per campi mancanti
                merged = {**DEFAULT_CONFIG, **data}
                return merged
        except Exception as e:
            log.warning(f"Config load error: {e}")
    # Fallback a variabili d'ambiente (backward compat)
    return {
        **DEFAULT_CONFIG,
        "rd": os.getenv("RD_API_KEY", ""),
        "tb": os.getenv("TB_API_KEY", ""),
    }


def save(data: dict) -> bool:
    """Scrive config.json"""
    try:
        # Valida i campi
        cfg = {
            "rd":      str(data.get("rd", "")),
            "tb":      str(data.get("tb", "")),
            "audio":   data.get("audio", "both"),
            "minQ":    int(data.get("minQ", 720)),
            "sort":    data.get("sort", "quality"),
            "sources": data.get("sources", DEFAULT_CONFIG["sources"]),
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        log.info(f"Config salvata in {CONFIG_PATH}")
        return True
    except Exception as e:
        log.error(f"Config save error: {e}")
        return False


def is_configured() -> bool:
    """True se almeno una API key è configurata"""
    cfg = load()
    return bool(cfg.get("rd") or cfg.get("tb"))
