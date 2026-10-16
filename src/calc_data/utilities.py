import time
from pathlib import Path

CACHE_DIR = Path("cache")
CACHE_TTL = 3600  # 1 hour in seconds
CACHE_VERSION = "v1"


def _cache_path() -> Path:
    """Return the path to the products cache file."""
    return CACHE_DIR / "gumroad_products.json"


def _debug_path() -> Path:
    """Return the path to the debug file inside the cache folder."""
    return CACHE_DIR / "gumroad_debug.json"


def _is_cache_valid(cache_file_path: Path) -> bool:
    """Return True if the cache file exists and is younger than CACHE_TTL."""
    if not cache_file_path.exists():
        return False
    try:
        file_modification_time = cache_file_path.stat().st_mtime
        return (time.time() - file_modification_time) < CACHE_TTL
    except OSError:
        return False


def _write_debug(raw_content: str) -> None:
    """Write raw JSON to debug file inside cache folder."""
    try:
        _debug_path().write_text(raw_content, encoding="utf-8")
    except OSError:
        pass

