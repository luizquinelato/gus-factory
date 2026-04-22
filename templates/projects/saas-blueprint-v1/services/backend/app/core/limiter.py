"""
limiter.py
==========
Instância global do rate limiter (slowapi).

Uso nos routers:
    from app.core.limiter import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...):
        ...

O limiter é registrado no app em main.py:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func extrai o IP do cliente para limitar por origem.
# Em produção atrás de um proxy (nginx/cloudflare), configure
# FORWARDED_ALLOW_IPS e use get_remote_address — o slowapi
# lê automaticamente X-Forwarded-For quando o proxy é confiável.
limiter = Limiter(key_func=get_remote_address)
