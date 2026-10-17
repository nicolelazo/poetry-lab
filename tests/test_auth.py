import json

import pytest
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from poetry_lab.auth import AuthConfigError, TokenQueryMiddleware, require_token

TOKEN = "t" * 40  # fake token, only for tests


async def inner_app(scope, receive, send):
    """Stand-in for the real MCP app: answers 200 'inside' to anything that gets through."""
    await PlainTextResponse("inside")(scope, receive, send)


@pytest.fixture
def client():
    return TestClient(TokenQueryMiddleware(inner_app, TOKEN))


def assert_404(response):
    assert response.status_code == 404
    assert response.text == "Not found"
    assert response.headers["content-type"].startswith("text/plain")
    assert "www-authenticate" not in response.headers
    assert TOKEN not in response.text


# ---------- the rejected cases ----------

def test_missing_token_gets_404(client):
    assert_404(client.post("/mcp", json={}))


def test_wrong_token_gets_404(client):
    assert_404(client.post("/mcp", json={}, params={"token": "x" * 40}))


@pytest.mark.parametrize(
    "token",
    ["", TOKEN + "x", TOKEN[:-1], TOKEN.upper(), "Bearer " + TOKEN],
)
def test_empty_or_near_miss_tokens_get_404(client, token):
    assert_404(client.post("/mcp", json={}, params={"token": token}))


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"])
def test_every_method_needs_the_token(client, method):
    assert client.request(method, "/mcp").status_code == 404


@pytest.mark.parametrize("path", ["/", "/mcp", "/mcp/", "/anything", "/.env", "/sse"])
def test_every_path_needs_the_token_even_unknown_ones(client, path):
    assert_404(client.get(path))


def test_token_in_header_or_path_is_not_accepted(client):
    assert client.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404
    assert client.get("/mcp", headers={"X-Api-Key": TOKEN}).status_code == 404
    assert client.get(f"/mcp/{TOKEN}").status_code == 404


def test_other_query_parameter_names_are_not_accepted(client):
    assert client.get("/mcp", params={"key": TOKEN}).status_code == 404


def test_rejection_never_uses_401_or_oauth_headers(client):
    for response in (client.get("/mcp"), client.get("/mcp", params={"token": "nope"})):
        assert response.status_code != 401
        assert "www-authenticate" not in response.headers


# ---------- the allowed case ----------

def test_correct_token_passes_through(client):
    response = client.post("/mcp", json={}, params={"token": TOKEN})
    assert response.status_code == 200 and response.text == "inside"


def test_correct_token_works_with_other_query_parameters(client):
    assert client.get("/mcp?a=1&token=" + TOKEN + "&b=2").status_code == 200


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
        TokenQueryMiddleware(inner_app, "weak")


def test_rejection_is_logged_without_the_token(client, caplog):
    with caplog.at_level("WARNING", logger="poetry_lab.auth"):
        client.post("/mcp", params={"token": "z" * 40})
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


def test_real_server_without_token_is_404(real_client):
    assert_404(real_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS))


def test_real_server_with_wrong_token_is_404(real_client):
    assert_404(real_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS, params={"token": "w" * 40}))


def test_real_server_with_right_token_initializes(real_client):
    response = real_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS, params={"token": TOKEN})
    assert response.status_code == 200
    data_line = next(l for l in response.text.splitlines() if l.startswith("data:")) if "data:" in response.text else response.text
    body = json.loads(data_line.removeprefix("data:").strip())
    assert body["result"]["serverInfo"]["name"] == "Poetry Lab"


def test_uvicorn_app_attribute_is_built_lazily_and_fails_closed(monkeypatch):
    import server
    from poetry_lab import config

    monkeypatch.setattr(config, "POETRY_TOKEN", "")
    server.__dict__.pop("app", None)
    with pytest.raises(SystemExit):
        server.app


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
