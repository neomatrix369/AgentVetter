---
name: av-disable
aliases: [tw-disable]
description: Turn AgentVetter enforcement OFF for Claude Code tool calls. Use when the user runs /av-disable or /tw-disable, or asks to disable, bypass, pause, or turn off AgentVetter guard/enforcement/blocking.
---

# av-disable

Flip the local AgentVetter kill switch OFF. This edits ONLY the `enable` key of `~/.agentvetter/config.json` — no Supabase writes, no other keys touched.

## Step 0 — Ask before disabling

**Stop and ask the user:** *Do you want to turn AgentVetter enforcement OFF?*

**Do not proceed to Step 1 until the user explicitly confirms.** If they decline or are unsure, stop with no config change.

## Step 1 — Set enable=false (python3 JSON round-trip)

Run exactly this (do not hand-edit the file with text tools):

```bash
python3 -c '
import json, os, sys, tempfile

p = os.path.expanduser("~/.agentvetter/config.json")
try:
    with open(p, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError("config is not a JSON object")
except FileNotFoundError:
    print(json.dumps({"ok": False, "reason": "missing", "action": "run `agentvetter setup-agent-hooks` first"}))
    sys.exit(1)
except (OSError, ValueError):
    # Never rebuild a broken config from defaults: that would silently allow every call.
    print(json.dumps({"ok": False, "reason": "unreadable", "action": "fix or re-run `agentvetter setup-agent-hooks`; config left unchanged"}))
    sys.exit(1)
cfg["enable"] = False
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".config.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
os.replace(tmp, p)  # atomic: a crash never leaves half-written JSON that denies every call
print(json.dumps({"ok": True, "enable": False}))
'
```

If the output has `"ok": false`, **stop**. Tell the user enforcement was NOT disabled, show the `action` text, and do not run Step 2's OFF message. Do not create or repair the config yourself.

## Step 2 — Confirm

Tell the user, plainly:

- AgentVetter enforcement is now **OFF** — the Claude Code hook allows every skill/MCP call without checking scan status. Enforcement is **fully bypassed**, including red-rated and never-scanned artifacts.
- Manual scanning and reporting still work while disabled: `/av-scan` submits scans and `/av-verify` reports status (its blocked **footer** shows what enforcement WOULD do, marked as currently bypassed).
- Re-enable at any time with `/av-enable`.
