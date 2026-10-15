"""Bearer token auth: every HTTP request must send 'Authorization: Bearer <MCP_TOKEN>'."""

import hmac
import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("poetry_lab.auth")

MIN_TOKEN_LENGTH = 32


class AuthConfigError(RuntimeError):
    """The token is missing or too weak. The server must not start."""


def require_token(token: str | None) -> str:
    """Return the token if it is usable, else raise. Never includes the token in the message."""
    if not token or token.startswith("replace-with"):
        raise AuthConfigError("MCP_TOKEN is not set. Put a long random value in .env (see .env.example).")
    if len(token) < MIN_TOKEN_LENGTH:
        raise AuthConfigError(f"MCP_TOKEN is too short. Use at least {MIN_TOKEN_LENGTH} random characters.")
    return token


class BearerAuthMiddleware:
    """Pure ASGI wrapper (so streaming responses keep working). Wrong or missing token gives 401."""

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

        logger.warning("Rejected request: missing or invalid bearer token")
        body = json.dumps({"error": "unauthorized"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _is_authorized(self, scope: Scope) -> bool:
        header = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                header = value
                break
        scheme, _, supplied = header.partition(b" ")
        if scheme.lower() != b"bearer":
            return False
        # Constant-time comparison so response time does not leak how much of the token matched.
        return hmac.compare_digest(supplied.strip(), self._expected)
