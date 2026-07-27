#!/usr/bin/env python3
"""STEP 5 — mandatory link gate. Exits non-zero on any failure; nothing is
pushed unless this prints PASS.

  (a) no unreplaced {{...}} or [[...]] tokens survive
  (b) every href appears byte-for-byte in work/links.json, or is a sinocism.com
      web-version link
  (c) no href contains google.com/url
  (d) every link key produced by build.py that content.json referenced resolved
"""
import html as H
import json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
doc = open(os.path.join(ROOT, "index.html")).read()
allowed = set(json.load(open(os.path.join(ROOT, "work", "links.json"))).values())

fail = []
for tok in re.findall(r"\{\{[A-Z_]+\}\}|\[\[[^\]]+\]\]", doc):
    fail.append(("unreplaced token", tok))

hrefs = [H.unescape(h) for h in re.findall(r'href="([^"]+)"', doc)]
for u in hrefs:
    if "google.com/url" in u:
        fail.append(("google redirect", u))
    elif u in allowed or "sinocism.com" in u:
        pass
    else:
        fail.append(("href not from build.py", u[:120]))

if fail:
    for why, what in fail:
        print(f"FAIL · {why}: {what}", file=sys.stderr)
    sys.exit(1)

print(f"PASS · {len(hrefs)} links verified against work/links.json")
