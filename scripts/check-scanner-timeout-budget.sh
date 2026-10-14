#!/usr/bin/env bash
# Assert tail scanner per-call timeouts fit under the SCAN_TIMEOUT envelope.
# Scanners run sequentially in run_all_scanners; Modal hard-kills the sandbox at
# TIMEOUT_SECONDS (300s in scan_app.py). This gate catches DepShield + Cargo Audit
# + Presend + Ossprey budget drift — see docs/ARCHITECTURE.md § Scanner timeout budget.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 <<'PY'
import re
import sys
from pathlib import Path

text = Path("sandbox/scanners.py").read_text(encoding="utf-8")

def _const(name: str) -> int:
    match = re.search(rf"^{name} = (\d+)", text, re.MULTILINE)
    if not match:
        print(f"FAIL: could not find {name} in sandbox/scanners.py")
        sys.exit(1)
    return int(match.group(1))

scan_timeout = _const("SCAN_TIMEOUT")
depshield = _const("DEPSHIELD_TIMEOUT")
cargo_audit = _const("CARGO_AUDIT_TIMEOUT")
presend = _const("PRESEND_TIMEOUT")
ossprey = _const("OSSPREY_TIMEOUT")
tail = depshield + cargo_audit + presend + ossprey

if tail > scan_timeout:
    print(
        f"FAIL: DEPSHIELD_TIMEOUT ({depshield}) + CARGO_AUDIT_TIMEOUT ({cargo_audit}) "
        f"+ PRESEND_TIMEOUT ({presend}) + OSSPREY_TIMEOUT ({ossprey}) = {tail} exceeds SCAN_TIMEOUT ({scan_timeout})"
    )
    sys.exit(1)

print(
    f"OK: tail scanner budget DEPSHIELD({depshield}) + CARGO_AUDIT({cargo_audit}) "
    f"+ PRESEND({presend}) + OSSPREY({ossprey}) <= SCAN_TIMEOUT({scan_timeout})"
)
PY
