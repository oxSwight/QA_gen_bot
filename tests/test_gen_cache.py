from pathlib import Path

from qa_gen_bot.gen_cache import load_gen_cache, save_gen_cache


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    files = {"src/test/java/com/demo/tests/T.java": "class T {}"}
    save_gen_cache(path, spec_path="x.json", package_hint="demo", files=files)
    assert load_gen_cache(path) == files
    assert load_gen_cache(path, expected_package_hint="demo") == files


def test_cache_package_hint_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    save_gen_cache(path, spec_path="a.json", package_hint="other", files={"x": "y"})
    try:
        load_gen_cache(path, expected_package_hint="demo")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("expected ValueError")
