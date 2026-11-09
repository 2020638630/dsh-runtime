import json
from pathlib import Path

import httpx
import pytest

from dsh_runtime import api_agent_connection_admin as admin
from dsh_runtime.api_agent_connections import Connection, ConnectionCatalog


SECRET = b"t" * 32
TEST_KEY = "synthetic-test-key"
OLD_KEY = "synthetic-existing-key"


def read_catalog(path):
    return admin.handle(path, {"action": "list"}, SECRET)


def command(action, revision, reference, provider, key=None):
    return dict(action=action, revision=revision, reference=reference, provider=provider, key=key)


def test_save_preserves_referenced_entries_and_rejects_stale_and_wrong_provider(tmp_path):
    path = tmp_path / "connections.local.json"
    path.write_text(json.dumps({"schema_version": 1, "connections": {"old": {
        "provider": "siliconflow", "base_url": "https://api.siliconflow.cn/v1", "api_key": OLD_KEY,
    }}}), encoding="utf-8")
    revision = read_catalog(path)["revision"]
    result = admin.handle(path, command("save", revision, "new", "openrouter", TEST_KEY), SECRET)
    assert result["status"] == "ok"
    assert result["connections"] == [
        {"reference": "new", "provider": "openrouter", "keySet": True},
        {"reference": "old", "provider": "siliconflow", "keySet": True},
    ]
    assert TEST_KEY not in json.dumps(result) and OLD_KEY not in json.dumps(result)
    catalog = ConnectionCatalog.from_file(path)
    assert catalog.get("old", "siliconflow").api_key == OLD_KEY
    assert catalog.get("new", "openrouter").api_key == TEST_KEY
    frozen = path.read_bytes()
    assert admin.handle(path, command("save", revision, "third", "openrouter", TEST_KEY), SECRET) == {
        "status": "conflict",
    }
    revision = result["revision"]
    assert admin.handle(path, command("save", revision, "old", "openrouter", TEST_KEY), SECRET) == {
        "status": "invalid",
    }
    assert admin.handle(path, command("save", revision, "old", "siliconflow"), SECRET) == result
    assert path.read_bytes() == frozen


def test_no_implicit_save_and_unsafe_paths_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "connections.local.json"
    result = read_catalog(path)
    assert result["connections"] == [] and not path.exists()
    monkeypatch.setattr(admin, "probe_connection", lambda entry: "authenticated")
    draft = command("test", result["revision"], "candidate", "openrouter", TEST_KEY)
    assert admin.handle(path, draft, SECRET) == {"status": "authenticated"}
    assert not path.exists()
    first = admin.handle(path, {**draft, "action": "save"}, SECRET)
    assert first["status"] == "ok"
    path.write_text("{malformed", encoding="utf-8")
    assert read_catalog(path) == {"status": "unavailable"}
    assert admin.handle(path, {**draft, "action": "save", "revision": first["revision"]}, SECRET) == {
        "status": "unavailable",
    }
    assert path.read_text(encoding="utf-8") == "{malformed"
    (tmp_path / ".git").mkdir()
    assert read_catalog(path) == {"status": "unavailable"}


def test_active_lock_and_failed_replace_leave_original_bytes(tmp_path, monkeypatch):
    path = tmp_path / "connections.local.json"
    result = read_catalog(path)
    create = command("save", result["revision"], "entry", "openrouter", TEST_KEY)
    assert admin.handle(path, create, SECRET)["status"] == "ok"
    original = path.read_bytes()
    update = command("save", read_catalog(path)["revision"], "entry", "openrouter", OLD_KEY)
    with admin._catalog_lock(path):
        assert admin.handle(path, update, SECRET) == {"status": "conflict"}
    def fail_replace(source: Path, destination: Path):
        raise OSError("synthetic replacement failure")
    monkeypatch.setattr(admin.os, "replace", fail_replace)
    assert admin.handle(path, update, SECRET) == {"status": "unavailable"}
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".dsh-api-*.tmp"))


@pytest.mark.parametrize(("provider", "base", "url", "body", "result"), [
    ("openrouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1/key",
     {"data": {"label": "ignored", "other": "not-reported"}}, "authenticated"),
    ("siliconflow", "https://api.siliconflow.cn/v1", "https://api.siliconflow.cn/v1/models?sub_type=chat",
     {"object": "list", "data": []}, "model_catalog_readable"),
])
def test_trials_make_one_non_generation_request(provider, base, url, body, result):
    seen = []
    def respond(request):
        seen.append(str(request.url))
        assert request.method == "GET" and not request.content
        assert request.headers["authorization"] == "Bearer " + TEST_KEY
        return httpx.Response(200, json=body)
    assert admin.probe_connection(Connection(provider, base, TEST_KEY),
                                  transport=httpx.MockTransport(respond)) == result
    assert seen == [url]


def test_trial_does_not_follow_redirect_or_return_provider_content():
    seen = []
    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://untrusted.invalid"})
    entry = Connection("openrouter", "https://openrouter.ai/api/v1", TEST_KEY)
    assert admin.probe_connection(entry, transport=httpx.MockTransport(redirect)) == "redirect_rejected"
    assert len(seen) == 1
    wrong = Connection("openrouter", "https://untrusted.invalid", TEST_KEY)
    assert admin.probe_connection(wrong, transport=httpx.MockTransport(redirect)) == "invalid"
    assert len(seen) == 1
    assert admin.probe_connection(entry, transport=httpx.MockTransport(
        lambda request: httpx.Response(401, text=TEST_KEY))) == "auth_rejected"
    assert admin.probe_connection(entry, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[]))) == "invalid_response"


@pytest.mark.parametrize(("provider", "url"), [
    ("openrouter", "https://openrouter.ai/api/v1/models"),
    ("siliconflow", "https://api.siliconflow.cn/v1/models?sub_type=chat"),
])
def test_model_catalog_projects_bounded_ids_from_fixed_get(provider, url, monkeypatch):
    monkeypatch.setattr(admin, "_MAX_MODELS", 2)
    seen = []

    def respond(request):
        seen.append((request.method, str(request.url)))
        assert request.headers["authorization"] == "Bearer " + TEST_KEY
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": "provider/chat", "name": TEST_KEY},
            {"id": "provider/chat"},
            {"id": TEST_KEY},
            {"id": "<invalid>"},
            {"id": "provider/second"},
            {"id": "provider/third"},
        ]})

    entry = Connection(provider, admin._ENDPOINTS[provider], TEST_KEY)
    assert admin.provider_models(entry, transport=httpx.MockTransport(respond)) == {
        "status": "ok", "models": ["provider/chat", "provider/second"], "truncated": True,
    }
    assert seen == [("GET", url)]


def test_model_lookup_uses_only_saved_matching_connection_and_current_revision(tmp_path, monkeypatch):
    path = tmp_path / "connections.local.json"
    revision = read_catalog(path)["revision"]
    lookup = {"action": "models", "reference": "entry", "provider": "openrouter", "revision": revision}
    assert admin.handle(path, lookup, SECRET) == {"status": "missing_connection"}
    saved = admin.handle(path, command("save", revision, "entry", "openrouter", TEST_KEY), SECRET)
    assert admin.handle(path, lookup, SECRET) == {"status": "conflict"}
    lookup["revision"] = saved["revision"]
    assert admin.handle(path, {**lookup, "key": OLD_KEY}, SECRET) == {"status": "invalid"}
    assert admin.handle(path, {**lookup, "provider": "siliconflow"}, SECRET) == {"status": "missing_connection"}
    seen = []

    def list_models(connection):
        seen.append(connection.api_key)
        return {"status": "ok", "models": ["provider/model"], "truncated": False}

    monkeypatch.setattr(admin, "provider_models", list_models)
    before = path.read_bytes()
    assert admin.handle(path, lookup, SECRET)["models"] == ["provider/model"]
    assert seen == [TEST_KEY] and path.read_bytes() == before
