"""Recheck the completed phone test from its saved artifacts. No inference is run."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import orion_chat_v2 as launcher

TEST = Path("/root/orion-read-test-szbb572y")


def finalize(test):
    source = launcher.CHAT / "home/.openclaw/workspace"
    target = test / "home/.openclaw/workspace"
    original_bytes = launcher.regular(test / "verification-report.json")
    original = json.loads(original_bytes)
    if original.get("test_directory") != str(test) or original.get("exit") != 0:
        raise ValueError("expected the completed isolated test")
    launcher.checked_workspace(source)
    launcher.checked_workspace(target)
    reply = launcher.regular(test / "reply.txt").decode()
    payload = reply.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",payload,flags=re.I)
    answer = json.loads(payload)
    if not isinstance(answer, dict):
        raise ValueError("saved answer must be a JSON object")
    records = launcher.events(test / "home/.openclaw",None)
    evidence = launcher.tool_evidence(records,target)
    note = launcher.regular(target / launcher.NOTE).decode()
    user = launcher.regular(target / "USER.md").decode()
    nonce = launcher.regular(target / "read-proof.txt").decode().strip()
    checks = launcher.verify_reply(reply,evidence,user,note,nonce)
    quote = answer.get("memory_quote")
    quote = quote if isinstance(quote,str) else ""
    bodies = re.split(r"\n## Excerpt \d+\n\nSource [^\n]*\n\n",note)[1:]
    outputs = [e.get("_text","") for e in evidence if e["target"]==launcher.NOTE and e["status"]=="SUCCESS"]
    report = {"result":"READ_VERIFY_STOP","original_report_sha256":hashlib.sha256(original_bytes).hexdigest(),
              "model_requests":0,"checks":checks,
              "quote_diagnostic":{"exact_in_note":bool(quote) and quote in note,
                                  "exact_in_excerpt":bool(quote) and any(quote in b for b in bodies),
                                  "whitespace_match_in_excerpt":bool(quote) and any(launcher.normalized_quote(quote) in launcher.normalized_quote(b) for b in bodies),
                                  "exact_in_tool_result":bool(quote) and any(quote in t for t in outputs),
                                  "whitespace_match_in_tool_result":bool(quote) and any(launcher.normalized_quote(quote) in launcher.normalized_quote(t) for t in outputs)}}
    if checks and all(checks.values()):
        launcher.install_update(source)
        report["result"]="READ_VERIFY_PASS"
        with tempfile.NamedTemporaryFile(mode="w",dir=launcher.CHAT,delete=False) as f:
            temp=Path(f.name);json.dump(report,f,indent=2);f.flush();os.fsync(f.fileno())
        temp.replace(launcher.CHAT / "read-verification-v2.json")
    if launcher.regular(test / "verification-report.json") != original_bytes:
        raise ValueError("original report changed")
    (test / "quote-verification-v2.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if report["result"]=="READ_VERIFY_PASS" else 1


if __name__=="__main__":
    os.umask(0o077)
    try:
        with (launcher.CHAT / "chat.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            sys.exit(finalize(TEST))
    except (OSError,ValueError,KeyError,TypeError) as error:
        print("READ_VERIFY_STOP",str(error),file=sys.stderr)
        sys.exit(1)
