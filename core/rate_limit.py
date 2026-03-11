"""
core/rate_limit.py
──────────────────
Rate Limiting 설정 (slowapi 기반).

사용법:
    from core.rate_limit import limiter
    @router.post("/endpoint")
    @limiter.limit("30/minute")
    async def my_endpoint(request: Request, ...):
        ...

main.py에서 app에 등록:
    from core.rate_limit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
