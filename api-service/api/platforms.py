from urllib.parse import urlparse
from api.config import settings

def classify_platform(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "unknown"

    hostname = hostname.lower()
    domain_to_platform = {
        "youtube.com": "youtube",
        "youtu.be": "youtube",
        "rutube.ru": "rutube",
        "vkvideo.ru": "vkvideo",
        "habr.com": "habr",
        "pikabu.ru": "pikabu",
        "dzen.ru": "dzen",
    }

    if hostname not in settings.VIDEO_LINKS + settings.ARTICLE_LINKS:
        return "unknown"

    for domain, platform in domain_to_platform.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            if platform == "dzen" and parsed.path.strip("/").split("/")[0] != "a":
                return "unknown"
            return platform

    return hostname

def normalize_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url