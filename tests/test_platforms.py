import pytest
from api.platforms import classify_platform, normalize_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/123", "youtube"),
        ("https://vkvideo.ru/12g344", "vkvideo"),
        ("https://dzen.ru/1232434", "unknown"),
        ("https://youtube.com/watch?v=123", "youtube"),
        ("https://habr.ru/123456", "unknown"),
        ("https://dzen.ru/a/123", "dzen"),
        ("https://example.com", "unknown"),
        ("https://asdkjkdafsktr", "unknown"),
        ("www.youtube.example.ru.com/watch?v=123", "unknown")
    ]
)
def test_platform(url, expected):
    assert classify_platform(url) == expected

@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtube.com/watch?v=123", "https://youtube.com/watch?v=123"),
        ("youtube.com/123", "https://youtube.com/123"),
        ("askdkasdk", "https://askdkasdk"),
        ("dzen.ru/a/123", "https://dzen.ru/a/123"),
    ]
)
def test_normalize_url(url, expected):
    assert normalize_url(url) == expected