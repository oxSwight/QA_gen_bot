"""Path safety for ZIP and disk writes."""
import pytest

from qa_gen_bot.safe_paths import (
    UnsafePathError,
    filter_safe_file_map,
    is_safe_relative_path,
    require_safe_file_map,
)


@pytest.mark.parametrize(
    "path",
    [
        "src/test/Ok.java",
        "pom.xml",
        "src/main/resources/schemas/a.json",
    ],
)
def test_safe_paths(path: str) -> None:
    assert is_safe_relative_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "../etc/passwd",
        "/etc/passwd",
        "src/../../outside.txt",
        "C:/Windows/system.ini",
        "src/test/\x00evil.java",
    ],
)
def test_unsafe_paths(path: str) -> None:
    assert not is_safe_relative_path(path)


def test_filter_drops_unsafe() -> None:
    files = {
        "pom.xml": "<p/>",
        "../evil.txt": "x",
        "src/Good.java": "class G {}",
    }
    safe, rejected = filter_safe_file_map(files)
    assert "../evil.txt" in rejected
    assert "pom.xml" in safe
    assert "src/Good.java" in safe


def test_require_safe_raises() -> None:
    with pytest.raises(UnsafePathError):
        require_safe_file_map({"../../x": "y"})
