"""URL token auth: every HTTP request must carry '?token=<POETRY_TOKEN>' in its URL."""

import logging
import secrets
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("poetry_lab.auth")

MIN_TOKEN_LENGTH = 32


class AuthConfigError(RuntimeError):
    """The token is missing or too weak. The server must not start."""


def require_token(token: str | None) -> str:
    """Return the token if it is usable, else raise. Never includes the token in the message."""
    if not token or token.startswith("replace-with"):
        raise AuthConfigError("POETRY_TOKEN is not set. Put a long random value in .env (see .env.example).")
    if len(token) < MIN_TOKEN_LENGTH:
        raise AuthConfigError(f"POETRY_TOKEN is too short. Use at least {MIN_TOKEN_LENGTH} random characters.")
    return token


class TokenQueryMiddleware:
    """Pure ASGI wrapper (so streaming responses keep working).

    A missing or wrong token gets a plain 404 'Not found': no 401 and no WWW-Authenticate header,
    so clients do not start an OAuth sign-in and strangers cannot tell the endpoint exists.
    """

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self._expected = require_token(token).encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # No other protocol (e.g. websocket) is served; refuse it.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return

        if self._is_authorized(scope):
            await self.app(scope, receive, send)
            return

        logger.warning("Rejected request: missing or invalid token")
        body = b"Not found"
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _is_authorized(self, scope: Scope) -> bool:
        params = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
        supplied = params.get("token", [""])[0].encode("utf-8")
        # Constant-time comparison so response time does not leak how much of the token matched.
        return secrets.compare_digest(supplied, self._expected)
