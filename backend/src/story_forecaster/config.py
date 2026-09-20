import os
from pathlib import Path
from typing import Any, Dict
import yaml

_SETTINGS_CACHE: Dict[str, Any] | None = None

def get_settings(reload: bool = False) -> Dict[str, Any]:
    """Loads and caches settings from config/settings.yaml."""
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None and not reload:
        return _SETTINGS_CACHE

    candidates = [
        Path(__file__).resolve().parents[3] / "config" / "settings.yaml",
        Path.cwd() / "config" / "settings.yaml",
        Path("config/settings.yaml").resolve()
    ]

    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        _SETTINGS_CACHE = data
                        return _SETTINGS_CACHE
            except Exception:
                pass

    _SETTINGS_CACHE = {}
    return _SETTINGS_CACHE
