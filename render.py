#!/usr/bin/env python3
"""STEP 4 — render work/content.json + work/links.json through template.html.

Link discipline: URLs are NEVER typed into content.json. Text carries
[[key|anchor text]] markers and story headlines carry a "k" field; this script
is the only place a real href is written, and it can only write URLs that came
out of build.py.
"""
import html as H
import json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "work")

LINKS = json.load(open(os.path.join(WORK, "links.json")))
C = json.load(open(os.path.join(WORK, "content.json")))

MARKER = re.compile(r"\[\[([A-Za-z0-9_]+)\|([^\]]+)\]\]")


def anchor(key, label):
    if key not in LINKS:
        sys.exit(f"FATAL: unknown link key {key!r} — not produced by build.py")
    return f'<a href="{H.escape(LINKS[key], quote=True)}">{H.escape(label)}</a>'


def rich(text):
    """Escape literal text, then expand [[key|label]] markers into anchors."""
    out, pos = [], 0
    for m in MARKER.finditer(text):
        out.append(H.escape(text[pos:m.start()]))
        out.append(anchor(m.group(1), m.group(2)))
        pos = m.end()
    out.append(H.escape(text[pos:]))
    return "".join(out)


def story(s):
    head = anchor(s["k"], s["h"]) if s.get("k") else H.escape(s["h"])
    p = [f'  <article class="story">',
         f'    <h3>{head}</h3>',
         f'    <p>{rich(s["s"])}</p>',
         f'    <div class="src">{H.escape(s["src"])}</div>']
    if s.get("followup"):
        p.append(f'    <span class="followup">{H.escape(s["followup"])}</span>')
    p.append('  </article>')
    return "\n".join(p)


def section(sec):
    p = ['<section class="section">',
         f'  <div class="section-head"><span class="tick"></span>'
         f'<h2>{H.escape(sec["title"])}</h2></div>']
    if sec.get("empty"):
        p.append(f'  <div class="card">{rich(sec["empty"])}</div>')
    for s in sec.get("stories", []):
        p.append(story(s))
    for g in sec.get("groups", []):
        p.append(f'  <div class="subhead">{H.escape(g["title"])}</div>')
        p.append('  <ul class="bullets">')
        for b in g["bullets"]:
            p.append(f'    <li>{rich(b)}</li>')
        p.append('  </ul>')
    if sec.get("note"):
        p.append(f'  <div class="card">{rich(sec["note"])}</div>')
    p.append('</section>')
    return "\n".join(p)


built = datetime.now(ZoneInfo("Australia/Sydney")).strftime("%a %-d %b %Y, %-I:%M%p").replace("AM","am").replace("PM","pm")
html = open(os.path.join(ROOT, "template.html")).read()
html = (html
        .replace("{{DATELINE}}", H.escape(C["dateline"]))
        .replace("{{SECTIONS}}", "\n\n".join(section(s) for s in C["sections"]))
        .replace("{{COMPILED}}", rich(C["compiled"]))
        .replace("{{MISSING}}", rich(C["missing"]))
        .replace("{{BUILT}}", H.escape(built)))

open(os.path.join(ROOT, "index.html"), "w").write(html)
n = len(re.findall(r'href="', html))
print(f"rendered index.html · {len(C['sections'])} sections · {n} links · built {built}")
