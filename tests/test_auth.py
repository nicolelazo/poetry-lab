import json

import pytest
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from poetry_lab.auth import AuthConfigError, BearerAuthMiddleware, require_token

TOKEN = "t" * 40  # fake token, only for tests


async def inner_app(scope, receive, send):
    """Stand-in for the real MCP app: answers 200 'inside' to anything that gets through."""
    await PlainTextResponse("inside")(scope, receive, send)


@pytest.fixture
def client():
    return TestClient(BearerAuthMiddleware(inner_app, TOKEN))


def assert_401(response):
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": "unauthorized"}
    assert "inside" not in response.text
    assert TOKEN not in response.text


# ---------- the 401 cases ----------

def test_missing_header_gets_401(client):
    assert_401(client.post("/mcp", json={}))


def test_wrong_token_gets_401(client):
    assert_401(client.post("/mcp", json={}, headers={"Authorization": "Bearer " + "x" * 40}))


@pytest.mark.parametrize(
    "header",
    [
        "Bearer",  # no token at all
        "Bearer ",  # empty token
        "Bearer " + TOKEN + "x",  # token plus one extra character
        "Bearer " + TOKEN[:-1],  # token missing the last character
        "Bearer " + TOKEN.upper(),  # wrong case
        "Basic " + TOKEN,  # wrong scheme
        "Token " + TOKEN,  # wrong scheme
        TOKEN,  # no scheme
        "BearerX " + TOKEN,  # sloppy scheme
    ],
)
def test_malformed_or_near_miss_headers_get_401(client, header):
    assert_401(client.post("/mcp", json={}, headers={"Authorization": header}))


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"])
def test_every_method_needs_the_token(client, method):
    assert client.request(method, "/mcp").status_code == 401


@pytest.mark.parametrize("path", ["/", "/mcp", "/mcp/", "/anything", "/.env", "/sse"])
def test_every_path_needs_the_token_even_unknown_ones(client, path):
    assert_401(client.get(path))


def test_token_in_query_string_or_other_header_is_not_accepted(client):
    assert client.get("/mcp", params={"token": TOKEN}).status_code == 401
    assert client.get("/mcp", headers={"X-Api-Key": TOKEN}).status_code == 401
    assert client.get(f"/mcp/{TOKEN}").status_code == 401


# ---------- the allowed case ----------

def test_correct_token_passes_through(client):
    response = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200 and response.text == "inside"


def test_scheme_is_case_insensitive_per_rfc(client):
    assert client.get("/mcp", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


# ---------- token rules (server must fail closed) ----------

@pytest.mark.parametrize("bad", [None, "", "short", "x" * 31, "replace-with-a-long-random-string"])
def test_unusable_tokens_are_refused(bad):
    with pytest.raises(AuthConfigError):
        require_token(bad)


def test_error_messages_never_contain_the_token():
    with pytest.raises(AuthConfigError) as err:
        require_token("secret-but-short")
    assert "secret-but-short" not in str(err.value)


def test_middleware_refuses_to_be_built_with_a_weak_token():
    with pytest.raises(AuthConfigError):
        BearerAuthMiddleware(inner_app, "weak")


def test_rejection_is_logged_without_the_token(client, caplog):
    with caplog.at_level("WARNING", logger="poetry_lab.auth"):
        client.post("/mcp", headers={"Authorization": "Bearer " + "z" * 40})
    assert "Rejected request" in caplog.text
    assert "z" * 40 not in caplog.text


# ---------- against the real MCP app ----------

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def real_client():
    import server

    app = server.create_app(TOKEN)
    # Host 127.0.0.1:8000 is on the server's allowed-host list.
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


def test_real_server_without_token_is_401(real_client):
    assert_401(real_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS))


def test_real_server_with_wrong_token_is_401(real_client):
    headers = {**MCP_HEADERS, "Authorization": "Bearer " + "w" * 40}
    assert_401(real_client.post("/mcp", json=INITIALIZE, headers=headers))


def test_real_server_with_right_token_initializes(real_client):
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"}
    response = real_client.post("/mcp", json=INITIALIZE, headers=headers)
    assert response.status_code == 200
    data_line = next(l for l in response.text.splitlines() if l.startswith("data:")) if "data:" in response.text else response.text
    body = json.loads(data_line.removeprefix("data:").strip())
    assert body["result"]["serverInfo"]["name"] == "Poetry Lab"


# ---------- Host header protection allows the ngrok domain only when configured ----------

def test_transport_security_allows_local_and_the_configured_domain():
    import server

    settings = server.transport_security("my-lab.ngrok-free.app")
    assert settings.enable_dns_rebinding_protection is True
    assert "my-lab.ngrok-free.app" in settings.allowed_hosts
    assert "https://my-lab.ngrok-free.app" in settings.allowed_origins
    assert "evil.example.com" not in settings.allowed_hosts


def test_transport_security_without_domain_is_local_only():
    import server

    settings = server.transport_security("")
    assert all(h.startswith(("127.0.0.1", "localhost", "[::1]")) for h in settings.allowed_hosts)
