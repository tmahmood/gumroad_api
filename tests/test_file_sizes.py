from pathlib import Path

import pytest

from calc_data import utilities


def test_collect_file_sizes_returns_filename_and_size(tmp_path: Path) -> None:
    first_file = tmp_path / "first.txt"
    first_file.write_text("hello")
    second_file = tmp_path / "second.txt"
    second_file.write_text("a longer body")

    file_summaries = utilities.collect_file_sizes([first_file, second_file])

    assert file_summaries == [
        {"filename": str(first_file), "file_size": 5},
        {"filename": str(second_file), "file_size": 13},
    ]


def test_collect_file_sizes_raises_when_file_reaches_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(b"0123456789")
    monkeypatch.setattr(utilities, "MAXIMUM_FILE_SIZE_BYTES", 10)

    with pytest.raises(ValueError, match="limit"):
        utilities.collect_file_sizes([file_path])


def test_collect_file_sizes_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        utilities.collect_file_sizes([tmp_path / "missing.txt"])


def test_collect_file_sizes_raises_for_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="regular file"):
        utilities.collect_file_sizes([tmp_path])
