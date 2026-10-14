"""Tests for the opt-in Presend adapter (typosquat + maintainer-change signals)."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest
import scanners

API = "https://presend.example"

FLAGGED_EVENT = {
    "version": "3.3.6",
    "publisher": "right9ctrl",
    "published": "2018-09-09",
    "previous_publisher": "dominictarr",
    "dormancy_days": 900,
    "reason": "new publisher after dormancy",
    "publisher_check": "done",
}


def _typosquat_result(name):
    suspicious = name in ("expres", "reqeusts")
    target = {"expres": "express", "reqeusts": "requests"}.get(name)
    return {
        "package": name,
        "suspicious": suspicious,
        "similar_to": [{"name": target, "distance": 1}] if target else [],
    }


def _maintainer_result(name):
    flagged = [FLAGGED_EVENT] if name == "event-stream" else []
    return {"package": name, "found": True, "suspicious": bool(flagged), "flagged_events": flagged}


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _FakeApi:
    """Stands in for urllib.request.urlopen and records every call."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail or {}

    def __call__(self, request, timeout=None):
        endpoint = request.full_url.rsplit("/", 1)[-1]
        payload = json.loads(request.data)
        self.calls.append((endpoint, payload, dict(request.header_items()), timeout))
        failure = self.fail.get(endpoint)
        if failure is not None:
            return failure(request, payload)
        make = _typosquat_result if endpoint == "typosquat-check" else _maintainer_result
        body = {"results": [make(name) for name in payload["packages"]]}
        return _FakeResponse(json.dumps(body).encode("utf-8"))


def _http_429(request, payload):
    raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", None, None)


def _write_npm(path: Path, deps: dict, dev: dict | None = None) -> None:
    data = {"dependencies": deps}
    if dev:
        data["devDependencies"] = dev
    path.write_text(json.dumps(data), encoding="utf-8")


def _run(workdir: Path, api: _FakeApi, monkeypatch: pytest.MonkeyPatch, url: str = API):
    monkeypatch.setenv("PRESEND_API_URL", url)
    with patch.object(scanners.urllib.request, "urlopen", side_effect=api):
        return scanners.run_presend(str(workdir), "package")


def test_given_no_url_when_run_presend_then_skipped_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"expres": "^4.0.0"})
    monkeypatch.delenv("PRESEND_API_URL", raising=False)
    api = _FakeApi()
    with patch.object(scanners.urllib.request, "urlopen", side_effect=api):
        findings, rows = scanners.run_presend(str(tmp_path), "package")
    assert findings == []
    assert rows[0]["status"] == "skipped_missing_credential"
    assert "PRESEND_API_URL" in rows[0]["detail"]
    assert api.calls == []


def test_given_non_http_url_when_run_presend_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"lodash": "^4.17.21"})
    api = _FakeApi()
    findings, rows = _run(tmp_path, api, monkeypatch, url="file:///etc/passwd")
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert api.calls == []


def test_given_no_manifest_when_run_presend_then_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings, rows = _run(tmp_path, _FakeApi(), monkeypatch)
    assert findings == []
    assert rows[0]["status"] == "not_applicable"


def test_given_only_local_specs_when_run_presend_then_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"a": "file:../a", "b": "workspace:*", "c": "npm:x@1"})
    api = _FakeApi()
    findings, rows = _run(tmp_path, api, monkeypatch)
    assert rows[0]["status"] == "not_applicable"
    assert api.calls == []


def test_given_npm_and_pypi_when_run_presend_then_amber_findings_and_only_names_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(
        tmp_path / "package.json",
        {"expres": "^4.0.0", "event-stream": "3.3.6", "local": "link:../local"},
        dev={"lodash": "^4.17.21"},
    )
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "requirements.txt").write_text(
        "reqeusts==2.0  # typo\n# comment\n-r base.txt\n./vendored\nflask>=3\n"
        "pkg @ https://example.com/pkg.whl\n",
        encoding="utf-8",
    )
    api = _FakeApi()
    findings, rows = _run(tmp_path, api, monkeypatch)

    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 3 + 3 + 2
    assert {f["severity"] for f in findings} == {"amber"}
    by_category = {(f["category"], f["package_name"]): f for f in findings}
    assert set(by_category) == {
        ("dependency_typosquat", "expres"),
        ("dependency_typosquat", "reqeusts"),
        ("dependency_maintainer_change", "event-stream"),
    }
    assert by_category[("dependency_typosquat", "reqeusts")]["file_path"] == "api/requirements.txt"
    change = by_category[("dependency_maintainer_change", "event-stream")]
    assert change["package_version"] == "3.3.6"
    assert "right9ctrl" in change["message"]
    assert change["advisory_url"] == "https://www.npmjs.com/package/event-stream"

    sent = {(endpoint, tuple(p["packages"])) for endpoint, p, _, _ in api.calls}
    assert sent == {
        ("typosquat-check", ("expres", "event-stream", "lodash")),
        ("maintainer-change-check", ("expres", "event-stream", "lodash")),
        ("typosquat-check", ("reqeusts", "flask")),
    }
    for _, payload, headers, timeout in api.calls:
        assert set(payload) == {"ecosystem", "packages"}
        assert headers["User-agent"] == scanners.PRESEND_USER_AGENT
        assert 0 < timeout <= scanners.PRESEND_REQUEST_TIMEOUT


def test_given_normalized_name_in_response_when_run_then_manifest_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "requirements.txt").write_text("Typing_Extensions\n", encoding="utf-8")

    def _normalized(request, payload):
        body = {"results": [{"package": "typing-extensions", "suspicious": True, "similar_to": []}]}
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    findings, rows = _run(tmp_path, _FakeApi(fail={"typosquat-check": _normalized}), monkeypatch)
    assert rows[0]["status"] == "completed"
    assert findings[0]["file_path"] == "requirements.txt"
    assert "on the curated list" in findings[0]["message"]


def test_given_rate_limited_batch_when_run_then_unreachable_and_partial_findings_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"expres": "^4.0.0"})
    api = _FakeApi(fail={"maintainer-change-check": _http_429})
    findings, rows = _run(tmp_path, api, monkeypatch)
    assert rows[0]["status"] == "unreachable"
    assert "HTTP 429" in rows[0]["detail"]
    assert [f["package_name"] for f in findings] == ["expres"]


def test_given_per_package_error_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"lodash": "^4.17.21"})

    def _package_error(request, payload):
        body = {"results": [{"package": "lodash", "error": "npm registry error (HTTP 502)"}]}
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    findings, rows = _run(
        tmp_path, _FakeApi(fail={"maintainer-change-check": _package_error}), monkeypatch
    )
    assert rows[0]["status"] == "unreachable"
    assert "HTTP 502" in rows[0]["detail"]


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"results": []}',
        b'["unexpected"]',
        b"x" * (scanners.PRESEND_MAX_RESPONSE_BYTES + 1),
    ],
)
def test_given_bad_response_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    api = _FakeApi(fail={"typosquat-check": lambda request, payload: _FakeResponse(body)})
    findings, rows = _run(tmp_path, api, monkeypatch)
    assert findings == []
    assert rows[0]["status"] == "unreachable"


def test_given_network_timeout_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

    def _timeout(request, payload):
        raise TimeoutError("timed out")

    findings, rows = _run(tmp_path, _FakeApi(fail={"typosquat-check": _timeout}), monkeypatch)
    assert rows[0]["status"] == "unreachable"
    assert "timed out" in rows[0]["detail"]


def test_given_budget_exhausted_when_run_then_unreachable_without_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    api = _FakeApi()
    clock = iter([0.0, float(scanners.PRESEND_TIMEOUT)])
    with patch.object(scanners.time, "monotonic", side_effect=lambda: next(clock)):
        findings, rows = _run(tmp_path, api, monkeypatch)
    assert rows[0]["status"] == "unreachable"
    assert "budget exhausted" in rows[0]["detail"]
    assert api.calls == []


def test_given_invalid_package_json_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    findings, rows = _run(tmp_path, _FakeApi(), monkeypatch)
    assert rows[0]["status"] == "unreachable"
    assert "invalid package.json" in rows[0]["detail"]


def test_given_non_object_package_json_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package.json").write_text("[]", encoding="utf-8")
    findings, rows = _run(tmp_path, _FakeApi(), monkeypatch)
    assert rows[0]["status"] == "unreachable"


def test_given_unreadable_manifest_when_run_then_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "requirements.txt").write_bytes(b"\xff\xfe\x00bad")
    findings, rows = _run(tmp_path, _FakeApi(), monkeypatch)
    assert rows[0]["status"] == "unreachable"
    assert "unreadable" in rows[0]["detail"]


def test_given_more_than_cap_when_run_then_truncation_surfaced_and_batched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = {f"pkg-{i:03d}": "^1.0.0" for i in range(scanners.PRESEND_MAX_PACKAGES + 5)}
    _write_npm(tmp_path / "package.json", deps)
    api = _FakeApi()
    findings, rows = _run(tmp_path, api, monkeypatch)
    assert rows[0]["status"] == "completed"
    assert "first 100 of 105" in rows[0]["detail"]
    maintainer_batches = [
        p["packages"] for e, p, _, _ in api.calls if e == "maintainer-change-check"
    ]
    assert len(maintainer_batches) == 5
    assert all(len(b) <= scanners.PRESEND_MAINTAINER_BATCH for b in maintainer_batches)
    assert "pkg-100" not in {name for b in maintainer_batches for name in b}


def test_given_non_dict_event_and_unavailable_check_when_run_then_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_npm(tmp_path / "package.json", {"left-pad": "1.3.0"})
    event = dict(FLAGGED_EVENT, publisher_check="unavailable", version=None)

    def _events(request, payload):
        body = {"results": [{"package": "left-pad", "flagged_events": ["junk", event]}]}
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    findings, rows = _run(
        tmp_path, _FakeApi(fail={"maintainer-change-check": _events}), monkeypatch
    )
    assert rows[0]["status"] == "completed"
    assert len(findings) == 1
    assert findings[0]["package_version"] is None
    assert "lookup unavailable" in findings[0]["message"]


def test_given_registry_when_listing_groups_then_presend_runs_before_ossprey() -> None:
    last = scanners.SCANNER_GROUPS[-2]
    assert last["sources"] == ["Presend"]
    assert last["applies_to"] == "both"
    for item_type in ("skill", "mcp_server", "package"):
        assert scanners._group_applies(last["applies_to"], item_type)


def test_given_group_runner_when_called_then_no_quality_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRESEND_API_URL", raising=False)
    findings, rows, quality = scanners._run_presend_group(str(tmp_path), "package", None)
    assert quality is None
    assert rows[0]["status"] == "skipped_missing_credential"


def test_given_more_manifests_than_cap_when_run_then_truncation_surfaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(scanners.DEPSHIELD_MAX_MANIFESTS + 2):
        sub = tmp_path / f"svc{i:02d}"
        sub.mkdir()
        (sub / "requirements.txt").write_text(f"pkg{i}\n", encoding="utf-8")
    findings, rows = _run(tmp_path, _FakeApi(), monkeypatch)
    assert rows[0]["status"] == "completed"
    assert "first 10 of 12 manifests read" in rows[0]["detail"]
