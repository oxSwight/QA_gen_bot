from qa_gen_bot.base_url import is_skip_base_url, normalize_base_url


def test_skip():
    assert is_skip_base_url("/skip")
    assert is_skip_base_url("/пропустить")


def test_normalize_https():
    url, err = normalize_base_url("https://dev.example.com/v1/")
    assert err is None
    assert url == "https://dev.example.com/v1"


def test_normalize_adds_scheme():
    url, err = normalize_base_url("dev.example.com/api")
    assert err is None
    assert url == "https://dev.example.com/api"


def test_invalid():
    _, err = normalize_base_url("not a url")
    assert err
