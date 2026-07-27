#!/usr/bin/env python3
"""STEP 6 — update the ledger and push, in one commit.

Usage: python3 publish.py '{"<gmail_id>":"YYYY-MM-DD", ...}' [today_iso]

Adds every id (summarized OR intentionally skipped) to processed.json, prunes
entries older than 30 days, commits index.html + processed.json, pushes to main.
"""
import datetime, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ids = json.loads(sys.argv[1])
today = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.date.today()

path = os.path.join(ROOT, "processed.json")
p = json.load(open(path))
p["processed"].update(ids)
cut = (today - datetime.timedelta(days=30)).isoformat()
p["processed"] = {k: v for k, v in
                  sorted(p["processed"].items(), key=lambda x: (x[1], x[0]), reverse=True)
                  if v >= cut}
json.dump(p, open(path, "w"), indent=1, ensure_ascii=False)


def git(*a):
    r = subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"FATAL git {' '.join(a)}\n{r.stderr.strip()}")
    return r.stdout.strip()


git("add", "index.html", "processed.json")
git("-c", "user.name=Daily Brief", "-c", "user.email=brief@local",
    "commit", "-m", f"Daily brief {today.isoformat()}")
git("push", "origin", "HEAD:main")
print(f"PUSHED · {len(ids)} new ledger entries · {len(p['processed'])} retained")
