"""Scenario: every scanner status the sandbox writes is allowed by the database.

Slice: status contract parity (duplicated status lists follow-up to the review).

The status check constraint on scan_run_scanners in db/schema.sql is the single
contract. If the sandbox writes a status missing from it, the insert fails at
runtime, so this test fails first.
"""

import re
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SANDBOX_DIR.parent / "db" / "schema.sql"


def _db_allowed_statuses() -> set[str]:
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    start = text.index("create table if not exists scan_run_scanners")
    block = text[start : text.index(");", start)]
    constraint = block[block.index("check (status in (") :]
    constraint = constraint[: constraint.index("))")]
    constraint = re.sub(r"--[^\n]*", "", constraint)
    return set(re.findall(r"'([a-z_]+)'", constraint))


def _statuses_written_by_scanners() -> set[str]:
    source = (SANDBOX_DIR / "scanners.py").read_text(encoding="utf-8")
    found = set(re.findall(r'"status": "([a-z_]+)"', source))
    found |= set(re.findall(r'status="([a-z_]+)"', source))
    return found


def test_given_schema_constraint_when_read_then_it_lists_the_known_statuses() -> None:
    """Scenario: the schema constraint lists the known statuses.

    Slice: status contract parity.
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Sandbox statuses match the database contract
    """
    ### Given / When
    allowed = _db_allowed_statuses()

    ### Then
    assert {"running", "completed", "failed", "unreachable"} <= allowed


def test_given_scanner_writes_when_compared_to_schema_then_every_status_is_allowed() -> None:
    """Scenario: every scanner status is allowed by the schema.

    Slice: status contract parity.
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Sandbox statuses match the database contract
    """
    ### Given
    allowed = _db_allowed_statuses()

    ### When
    written = _statuses_written_by_scanners()

    ### Then
    assert written, "expected scanners.py to write at least one status literal"
    assert written - allowed == set(), (
        f"statuses missing from schema constraint: {written - allowed}"
    )
