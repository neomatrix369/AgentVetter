"""Unit tests for _acquire_target dispatch logic.

Author: agentvetter
Created: 2026-08-01
Scope: git clone, local copy, archive upload/extract, filesystem-path guard,
       introspection-only empty workdir; _is_git_url / _maybe_pack_local_target

Tests the paths (git clone, local copy, archive extract, introspection-only)
using tmp dirs and subprocess mocking — no network, no Modal, no Supabase.
"""

import os
import subprocess
import sys
import tarfile
import types
from io import BytesIO
from unittest.mock import patch

import pytest

# scan_app imports `modal` and `supabase` at module level; stub them so the
# test suite works without those heavy dependencies installed.
for _mod in ("modal", "supabase"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# modal.App, modal.Image, modal.Secret — used at import-time by scan_app
_modal = sys.modules["modal"]


class _FakeImage:
    def debian_slim(self, **kw):
        return self

    def apt_install(self, *a):
        return self

    def run_commands(self, *a):
        return self

    def pip_install(self, *a):
        return self

    def add_local_python_source(self, *a, **kw):
        return self


class _FakeApp:
    def __init__(self, *a, **kw):
        pass

    def function(self, **kw):
        def decorator(fn):
            return fn

        return decorator

    def local_entrypoint(self, **kw):
        def decorator(fn):
            return fn

        return decorator


class _FakeSecret:
    @staticmethod
    def from_name(n):
        return n


_modal.App = _FakeApp  # type: ignore[attr-defined]
_modal.Image = _FakeImage()  # type: ignore[attr-defined]
_modal.Secret = _FakeSecret  # type: ignore[attr-defined]

from scan_app import (  # noqa: E402
    _acquire_target,
    _extract_archive,
    _is_git_url,
    _looks_like_filesystem_path,
    _maybe_pack_local_target,
    _normalize_github_clone_url,
    _pack_local_dir,
    main,
)

# ── _is_git_url classification ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/org/repo.git",
        "https://github.com/org/repo",
        "git://github.com/org/repo.git",
        "git@github.com:org/repo.git",
        "ssh://git@github.com/org/repo.git",
        "https://gitlab.example.com/team/project",
    ],
)
def test_is_git_url_recognises_git_urls(url):
    assert _is_git_url(url) is True


@pytest.mark.parametrize(
    "target",
    [
        "/tmp/local-skill",
        "./relative/path",
        "stdio://some-mcp-server",
        "http://mcp-server.example.com:8080/sse",
        "https://api.everesteer.ai/mcp/",
    ],
)
def test_is_git_url_rejects_non_git_targets(target):
    assert _is_git_url(target) is False


# ── Filesystem-path detection ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "target",
    [
        "./fixtures/skills/vuln-prompt-injection-notes",
        "/abs/path/to/skill",
        "relative/skill-dir",
    ],
)
def test_looks_like_filesystem_path_for_host_paths(target):
    assert _looks_like_filesystem_path(target) is True


@pytest.mark.parametrize(
    "target",
    [
        "stdio://my-mcp-server",
        "http://localhost:8080/sse",
        "https://github.com/org/repo",
        "git@github.com:org/repo.git",
    ],
)
def test_looks_like_filesystem_path_rejects_protocol_targets(target):
    assert _looks_like_filesystem_path(target) is False


# ── Git clone path ──────────────────────────────────────────────────────────


def test_github_browse_url_normalizes_to_clone_url():
    """
    Scenario: GitHub browse paths are never passed to git clone.
    Slice: slice-62 GWT-62.1

    Given a GitHub tree browse URL,
    When the sandbox normalizes the clone URL,
    Then only the repository URL remains.
    """
    ### Given
    browse_url = "https://github.com/org/repo/tree/main/skills/foo"

    ### When
    actual_clone_url = _normalize_github_clone_url(browse_url)

    ### Then
    assert actual_clone_url == "https://github.com/org/repo", (
        "GitHub browse URLs must normalize before cloning"
    )


def test_acquire_target_normalizes_github_browse_url_before_clone(tmp_path):
    workdir = str(tmp_path / "scan-target")
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    browse_url = "https://github.com/org/repo/blob/main/skills/foo/SKILL.md"

    with patch("scan_app.subprocess.run", return_value=fake_result) as mock_run:
        _acquire_target(browse_url, "skill", workdir)

    assert "https://github.com/org/repo" in mock_run.call_args[0][0]


def test_acquire_target_clones_git_url(tmp_path):
    workdir = str(tmp_path / "scan-target")
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("scan_app.subprocess.run", return_value=fake_result) as mock_run:
        _acquire_target("https://github.com/org/repo.git", "skill", workdir)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "git"
    assert "clone" in args
    assert "--depth" in args
    assert "https://github.com/org/repo.git" in args
    assert workdir in args
    # Given a URL that starts with "-", git must not read it as an option.
    assert args.index("--") < args.index("https://github.com/org/repo.git")
    assert os.path.isdir(workdir)


def test_acquire_target_raises_on_clone_failure(tmp_path):
    workdir = str(tmp_path / "scan-target")
    fake_result = subprocess.CompletedProcess(
        args=[], returncode=128, stdout="", stderr="fatal: repo not found"
    )

    with patch("scan_app.subprocess.run", return_value=fake_result):
        with pytest.raises(RuntimeError, match="git clone failed"):
            _acquire_target("https://github.com/org/repo.git", "skill", workdir)


# ── Local copy path ─────────────────────────────────────────────────────────


def test_acquire_target_copies_local_directory(tmp_path):
    src = tmp_path / "source-skill"
    src.mkdir()
    (src / "SKILL.md").write_text("# Test skill")
    (src / "sub").mkdir()
    (src / "sub" / "helper.py").write_text("pass")

    workdir = str(tmp_path / "scan-target")
    _acquire_target(str(src), "skill", workdir)

    assert os.path.isfile(os.path.join(workdir, "SKILL.md"))
    assert os.path.isfile(os.path.join(workdir, "sub", "helper.py"))


# ── Archive upload path (host → Modal) ──────────────────────────────────────


def test_pack_and_extract_roundtrip_preserves_skill_md(tmp_path):
    """
    Scenario: Host packs a fixture dir; remote extract restores SKILL.md.
    Slice: local-path upload

    Given a local skill directory with SKILL.md and a nested file,
    When it is packed then extracted into a fresh workdir,
    Then both files are present under the workdir.
    """
    ### Given
    src = tmp_path / "fixture-skill"
    src.mkdir()
    (src / "SKILL.md").write_text("# Injected skill\n")
    (src / "notes").mkdir()
    (src / "notes" / "extra.txt").write_text("payload")
    workdir = str(tmp_path / "scan-target")
    os.makedirs(workdir)

    ### When
    archive = _pack_local_dir(str(src))
    _extract_archive(archive, workdir)

    ### Then
    assert os.path.isfile(os.path.join(workdir, "SKILL.md")), "SKILL.md missing after extract"
    assert os.path.isfile(os.path.join(workdir, "notes", "extra.txt")), "nested file missing"


def _normalized_tar_names(archive: bytes) -> set[str]:
    names: set[str] = set()
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            rel = member.name.lstrip("./")
            if rel:
                names.add(rel)
    return names


def _write_evals_tree(root) -> None:
    evals = root / "evals" / "scenario-1"
    evals.mkdir(parents=True)
    (evals / "task.md").write_text("# corpus")
    nested = root / "notes" / "evals"
    nested.mkdir(parents=True)
    (nested / "keep.txt").write_text("not tessl corpus")
    (root / "SKILL.md").write_text("# skill")


@pytest.mark.parametrize(
    "marker",
    ["tessl.json", ".tessl-plugin"],
)
def test_given_tessl_plugin_when_packed_then_root_evals_is_omitted(tmp_path, marker):
    """
    Scenario: Host Tessl evals corpus is not a vuln-scan input.
    Slice: slice-48 GWT-48.5

    Given a local Tessl plugin with host evals/ and a nested notes/evals/,
    When it is packed for Modal,
    Then root evals/ is absent and other skill files remain.
    """
    ### Given
    src = tmp_path / "tessl-skill"
    src.mkdir()
    _write_evals_tree(src)
    if marker == "tessl.json":
        (src / "tessl.json").write_text("{}")
    else:
        (src / ".tessl-plugin").mkdir()

    ### When
    names = _normalized_tar_names(_pack_local_dir(str(src)))

    ### Then
    assert "SKILL.md" in names
    assert "notes/evals/keep.txt" in names
    assert not any(n == "evals" or n.startswith("evals/") for n in names)


def test_given_tessl_plugin_when_copied_locally_then_root_evals_is_omitted(tmp_path):
    """
    Scenario: Same-machine acquire matches the Modal pack exclude.
    Slice: slice-48 GWT-48.5

    Given a Tessl plugin directory on disk,
    When _acquire_target copies it without an archive,
    Then root evals/ is absent from the workdir.
    """
    ### Given
    src = tmp_path / "tessl-skill"
    src.mkdir()
    _write_evals_tree(src)
    (src / "tessl.json").write_text("{}")
    workdir = str(tmp_path / "scan-target")

    ### When
    _acquire_target(str(src), "skill", workdir)

    ### Then
    assert os.path.isfile(os.path.join(workdir, "SKILL.md"))
    assert os.path.isfile(os.path.join(workdir, "notes", "evals", "keep.txt"))
    assert not os.path.exists(os.path.join(workdir, "evals"))


def test_given_non_tessl_skill_when_packed_then_evals_is_kept(tmp_path):
    """
    Scenario: Non-Tessl trees are not stripped of an evals/ folder.
    Slice: slice-48 GWT-48.6

    Given a local skill with no Tessl root marker and an evals/ folder,
    When it is packed,
    Then evals/ is present in the archive.
    """
    ### Given
    src = tmp_path / "plain-skill"
    src.mkdir()
    _write_evals_tree(src)

    ### When
    names = _normalized_tar_names(_pack_local_dir(str(src)))

    ### Then
    assert "evals/scenario-1/task.md" in names
    assert "SKILL.md" in names


def test_given_path_traversal_archive_when_extracting_then_it_is_rejected_without_writing_outside(
    tmp_path,
):
    """
    Scenario: Uploaded archives cannot escape the sandbox work directory.
    Slice: archive acquisition safety

    Given a tar archive containing a ../ path traversal member,
    When the sandbox extracts it,
    Then extraction raises and no file is created outside the requested workdir.
    """
    ### Given
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    escaped = tmp_path / "escaped.txt"
    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as tar:
        member = tarfile.TarInfo("../escaped.txt")
        data = b"unsafe"
        member.size = len(data)
        tar.addfile(member, BytesIO(data))

    ### When / Then
    with pytest.raises(tarfile.FilterError):
        _extract_archive(payload.getvalue(), str(workdir))
    assert not escaped.exists()


def test_maybe_pack_local_target_returns_bytes_for_directory(tmp_path):
    ### Given
    src = tmp_path / "skill"
    src.mkdir()
    (src / "SKILL.md").write_text("x")

    ### When
    archive = _maybe_pack_local_target(str(src))

    ### Then
    assert archive is not None
    assert isinstance(archive, bytes)
    assert len(archive) > 0


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/org/repo.git",
        "stdio://mcp",
        "http://localhost:8080/sse",
        "/no/such/directory-on-host",
    ],
)
def test_maybe_pack_local_target_returns_none_when_not_local_dir(target):
    assert _maybe_pack_local_target(target) is None


def test_acquire_target_extracts_uploaded_archive(tmp_path):
    """
    Scenario: Remote sandbox receives archive bytes and populates workdir.
    Slice: local-path upload

    Given a packed local skill and a remote-style path that does not exist on disk,
    When _acquire_target is called with target_archive,
    Then SKILL.md appears in workdir (upload path, not local copy).
    """
    ### Given
    src = tmp_path / "host-skill"
    src.mkdir()
    (src / "SKILL.md").write_text("# From host\n")
    archive = _pack_local_dir(str(src))
    workdir = str(tmp_path / "scan-target")
    # Path string looks local but is absent on this "remote" filesystem:
    remote_looking = str(tmp_path / "does-not-exist-on-remote" / "vuln-skill")

    ### When
    _acquire_target(remote_looking, "skill", workdir, target_archive=archive)

    ### Then
    skill_path = os.path.join(workdir, "SKILL.md")
    assert os.path.isfile(skill_path), "expected SKILL.md from uploaded archive"
    assert open(skill_path).read() == "# From host\n"


def test_given_local_target_when_host_entrypoint_runs_then_it_hands_the_archive_to_modal() -> None:
    """
    Scenario: Local source crosses the host-to-sandbox boundary as an archive.
    Slice: production Modal handoff

    Given the host can pack a local target,
    When the Modal entrypoint starts a scan,
    Then scan_item.remote receives the target identity and exact archive bytes.
    """
    ### Given
    archive = b"packed-local-target"

    ### When
    with (
        patch("scan_app._maybe_pack_local_target", return_value=archive) as pack,
        patch("scan_app.scan_item") as scan_item,
    ):
        main("fixtures/skill", "skill", "item-1", "run-1")

    ### Then
    pack.assert_called_once_with("fixtures/skill")
    scan_item.remote.assert_called_once_with(
        target="fixtures/skill",
        item_type="skill",
        item_id="item-1",
        scan_run_id="run-1",
        target_archive=archive,
    )


def test_given_manifest_key_and_pack_path_when_entrypoint_runs_then_packs_pack_path() -> None:
    """
    Scenario: Manifest MCP keys keep key identity while packing the fixture dir.
    Slice: demo-mcp.json / key-only identity

    Given target is a bare MCP config key and pack_path is a local server dir,
    When the Modal entrypoint starts,
    Then packing uses pack_path and remote still sees the key as target.
    """
    ### Given
    archive = b"packed-mcp-fixture"

    ### When
    with (
        patch("scan_app._maybe_pack_local_target", return_value=archive) as pack,
        patch("scan_app.scan_item") as scan_item,
    ):
        main(
            "safe-tool",
            "mcp_server",
            "item-1",
            "run-1",
            pack_path="/abs/fixtures/mcp/safe-time-server",
        )

    ### Then
    pack.assert_called_once_with("/abs/fixtures/mcp/safe-time-server")
    scan_item.remote.assert_called_once_with(
        target="safe-tool",
        item_type="mcp_server",
        item_id="item-1",
        scan_run_id="run-1",
        target_archive=archive,
    )


def test_acquire_target_raises_when_local_path_missing_without_archive(tmp_path):
    """
    Scenario: Filesystem-looking target with no upload fails loudly (no empty workdir).
    Slice: local-path upload guard

    Given a host-style path that is not on disk and no target_archive,
    When _acquire_target runs,
    Then it raises RuntimeError instead of silently leaving an empty workdir.
    """
    ### Given
    workdir = str(tmp_path / "scan-target")
    missing = str(tmp_path / "fixtures" / "skills" / "missing-skill")

    ### When / Then
    with pytest.raises(RuntimeError, match="no archive uploaded"):
        _acquire_target(missing, "skill", workdir)


# ── Introspection-only path ─────────────────────────────────────────────────


def test_acquire_target_creates_empty_workdir_for_introspection(tmp_path):
    workdir = str(tmp_path / "scan-target")
    _acquire_target("stdio://my-mcp-server", "mcp_server", workdir)

    assert os.path.isdir(workdir)
    assert os.listdir(workdir) == []


def test_acquire_target_creates_empty_workdir_for_http_mcp(tmp_path):
    """HTTP MCP servers are introspection-only (not git repos)."""
    workdir = str(tmp_path / "scan-target")
    _acquire_target("http://localhost:8080/sse", "mcp_server", workdir)

    assert os.path.isdir(workdir)
    assert os.listdir(workdir) == []


def test_acquire_target_creates_empty_workdir_for_https_mcp(tmp_path):
    """HTTPS MCP endpoints are introspection-only and must not be git-cloned."""
    workdir = str(tmp_path / "scan-target")
    _acquire_target("https://api.everesteer.ai/mcp/", "mcp_server", workdir)

    assert os.path.isdir(workdir)
    assert os.listdir(workdir) == []
