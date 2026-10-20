import time
from pathlib import Path
from typing import TypedDict

CACHE_DIR = Path("cache")
CACHE_TTL = 3600  # 1 hour in seconds
CACHE_VERSION = "v1"

BYTES_PER_GIGABYTE = 1024**3
MAXIMUM_FILE_SIZE_BYTES = 20 * BYTES_PER_GIGABYTE


class FileSummary(TypedDict):
    """Name and size in bytes of a single file."""

    filename: str
    file_size: int


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


def collect_file_sizes(file_paths: list[str | Path]) -> list[FileSummary]:
    """Summarize files by name and size in bytes.

    Args:
        file_paths: Paths of the files to inspect.

    Returns:
        One dict per file with ``filename`` (the full path) and ``file_size``
        keys, in the same order as ``file_paths``.

    Raises:
        FileNotFoundError: If a path does not exist.
        ValueError: If a path is not a regular file, or if a file is 20 GB
            or larger.
        OSError: If a file's metadata cannot be read.
    """
    file_summaries: list[FileSummary] = []
    for file_path_value in file_paths:
        file_path = Path(file_path_value)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a regular file: {file_path}")

        file_size_bytes = file_path.stat().st_size
        if file_size_bytes >= MAXIMUM_FILE_SIZE_BYTES:
            raise ValueError(
                f"File {file_path} is {file_size_bytes} bytes, which is at or "
                f"above the {MAXIMUM_FILE_SIZE_BYTES}-byte (20 GB) limit"
            )

        file_summaries.append(
            {"filename": str(file_path), "file_size": file_size_bytes}
        )
    return file_summaries

