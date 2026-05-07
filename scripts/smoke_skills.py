#!/usr/bin/env python3
"""All-skill health check harness — the hardening path for the no-skill-whitelist
decision: instead of hiding non-core skills during demos, assert that every
registered skill stays callable on demo data.

For every manifest under zw_brain/skill_registration/registered/*.json:
  - POST {} to http://<host>:<port>/api/skills/<skill_id>
  - status < 500 and JSON-parseable body  → healthy (callable; input validation
    or runtime returns a structured response, even if it's an error or empty)
  - status >= 500, network failure, or unparseable body → unhealthy

Exits 1 when any skill is unhealthy. Writes a JSON report regardless.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_ROOT / "zw_brain" / "skill_registration" / "registered"


def call_skill(host: str, port: int, skill_id: str, timeout: float) -> dict[str, Any]:
    url = f"http://{host}:{port}/api/skills/{skill_id}"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read()
        try:
            json.loads(body)
            parsed_ok = True
        except Exception:
            parsed_ok = False
        return {
            "skill_id": skill_id,
            "status": resp.status,
            "healthy": resp.status < 500 and parsed_ok,
            "parsed_ok": parsed_ok,
            "error": None if parsed_ok else "non-json body",
        }
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            json.loads(body)
            parsed_ok = True
        except Exception:
            parsed_ok = False
        return {
            "skill_id": skill_id,
            "status": e.code,
            "healthy": e.code < 500 and parsed_ok,
            "parsed_ok": parsed_ok,
            "error": None if e.code < 500 and parsed_ok else f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "skill_id": skill_id,
            "status": None,
            "healthy": False,
            "parsed_ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="zw-brain all-skill health check")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--timeout", type=float, default=10.0, help="per-skill HTTP timeout (sec)")
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / ".data" / "trial-up-report.json",
        help="output JSON report path",
    )
    parser.add_argument(
        "--max-failures-shown",
        type=int,
        default=20,
        help="cap stderr summary of unhealthy skills to keep output readable",
    )
    args = parser.parse_args()

    skill_files = sorted(REGISTRY_DIR.glob("*.json"))
    if not skill_files:
        print(f"[smoke_skills] FAIL: no skill manifests under {REGISTRY_DIR}", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for sf in skill_files:
        try:
            manifest = json.loads(sf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[smoke_skills] WARN: cannot read {sf.name}: {e}", file=sys.stderr)
            continue
        skill_id = manifest.get("skill_id") or manifest.get("slug")
        if not skill_id or skill_id in seen_ids:
            continue
        seen_ids.add(skill_id)
        results.append(call_skill(args.host, args.port, skill_id, args.timeout))

    healthy = [r for r in results if r["healthy"]]
    unhealthy = [r for r in results if not r["healthy"]]
    summary = {
        "total_manifests": len(skill_files),
        "checked": len(results),
        "healthy": len(healthy),
        "unhealthy": len(unhealthy),
        "unhealthy_skill_ids": [r["skill_id"] for r in unhealthy],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[smoke_skills] manifests={summary['total_manifests']} "
        f"checked={summary['checked']} "
        f"healthy={summary['healthy']} "
        f"unhealthy={summary['unhealthy']}"
    )
    print(f"[smoke_skills] report: {args.report}")

    if unhealthy:
        print(
            f"[smoke_skills] FAIL: {len(unhealthy)} unhealthy skill(s) "
            f"(showing first {min(args.max_failures_shown, len(unhealthy))}):",
            file=sys.stderr,
        )
        for r in unhealthy[: args.max_failures_shown]:
            print(
                f"  - {r['skill_id']:<50}  status={r['status']}  err={r['error']}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
