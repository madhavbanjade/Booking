import httpx

from app.config import settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token: str | None) -> bool:
    """Check a Cloudflare Turnstile token. Skipped when no secret key is set."""
    if not settings.turnstile_secret_key:
        return True
    if not token:
        return False
    try:
        response = httpx.post(
            VERIFY_URL,
            data={"secret": settings.turnstile_secret_key, "response": token},
            timeout=10,
        )
        return bool(response.json().get("success"))
    except (httpx.HTTPError, ValueError):
        return False
