from fastapi import Request
from slowapi import Limiter

from app.config import get_settings


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    X-Forwarded-For can be forged by clients, so only the entry appended by OUR
    proxies is trusted: the Nth entry from the right, where N is TRUSTED_PROXY_HOPS.
    With 0 hops (local development) the direct socket address is used.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


# In-memory counters: per process, reset on restart (see the notes at the end of Phase 13)
limiter = Limiter(key_func=client_ip)
