"""
Edge Layer — simulates WAF, DDoS protection, rate limiting,
and security headers that sit in front of a real banking API.

In production, this would be AWS WAF + CloudFront + API Gateway.
Here we implement the same concepts in middleware.

Checks (in order):
  1. IP blocklist (banned abusers)
  2. WAF body scan (SQL injection, XSS, path traversal)
  3. Process request
  4. Add security headers to response
  5. Log request method, path, status, latency
"""
import time
import logging
from urllib import request, response
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("edge_layer")

# In production: maintained by security team, fed by threat intel
BLOCKED_IPS: set[str] = set()

# Simplified WAF rules — block common attack patterns
BLOCKED_PATTERNS = [
    "<script>",         # XSS
    "DROP TABLE",       # SQL injection
    "'; --",            # SQL injection
    "../../../",        # Path traversal
    "UNION SELECT",     # SQL injection
    "javascript:",      # XSS
]


class EdgeLayerMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"

        # ── 1. IP blocklist ───────────────────────────
        if client_ip in BLOCKED_IPS:
            logger.warning(f"[EDGE] Blocked IP: {client_ip}")
            return Response(
                content='{"detail":"Forbidden"}',
                status_code=403,
                media_type="application/json",
            )

        # ── 2. WAF body scan ──────────────────────────
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            body_str = body.decode("utf-8", errors="ignore")
            for pattern in BLOCKED_PATTERNS:
                if pattern.lower() in body_str.lower():
                    logger.warning(
                        f"[EDGE/WAF] Blocked '{pattern}' from {client_ip} "
                        f"on {request.url.path}"
                    )
                    return Response(
                        content='{"detail":"Request blocked by WAF"}',
                        status_code=403,
                        media_type="application/json",
                    )

        # ── 3. Process request ────────────────────────
        response = await call_next(request)

        # ── 4. Security headers ───────────────────────
        
        # ── 4. Security headers ───────────────────────
        path = request.url.path
        if path not in ("/", "/docs", "/openapi.json", "/redoc"):
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Cache-Control"] = "no-store"

        # ── 5. Log request ────────────────────────────
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"[EDGE] {request.method} {request.url.path} "
            f"→ {response.status_code} ({duration:.0f}ms) "
            f"from {client_ip}"
        )

        return response