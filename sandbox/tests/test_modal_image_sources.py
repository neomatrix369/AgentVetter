"""Scenario: every sandbox module scan_app imports is baked into the Modal image.

Slice: Modal image source parity (regression from the redaction change, PR #212).

Local tests put sandbox/ on sys.path, so a missing module only fails on a remote
Modal worker. This test reads scan_app.py and checks each sandbox import is
listed with add_local_python_source.
"""

import re
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parents[1]
SCAN_APP = SANDBOX_DIR / "scan_app.py"


def _sandbox_modules() -> set[str]:
    source = SCAN_APP.read_text(encoding="utf-8")
    imported = set(re.findall(r"^from (\w+) import", source, flags=re.MULTILINE))
    return {name for name in imported if (SANDBOX_DIR / f"{name}.py").exists()}


def _baked_modules() -> set[str]:
    source = SCAN_APP.read_text(encoding="utf-8")
    return set(re.findall(r'add_local_python_source\("(\w+)"', source))


def test_given_scan_app_imports_when_compared_to_image_then_every_sandbox_module_is_baked() -> None:
    ### Given
    needed = _sandbox_modules()

    ### When
    baked = _baked_modules()

    ### Then
    assert needed, "expected scan_app.py to import at least one sandbox module"
    assert needed - baked == set(), f"sandbox modules not baked into the Modal image: {needed - baked}"
