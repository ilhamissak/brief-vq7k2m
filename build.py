#!/usr/bin/env python3
"""STEP 2/3 — parse saved Gmail get_message JSON files.

Usage:  python3 build.py <slug>=<path.json> [<slug>=<path.json> ...]

For each email writes work/<slug>.txt : the editorial text with boilerplate
stripped and every real link replaced by an inline [[key]] marker.
Writes work/links.json : {key: VERBATIM href} (WSJ trk links deterministically
base64-decoded to clean wsj.com URLs; everything else byte-for-byte verbatim).

Prints counts ONLY. Never print link tables or full text — that is the whole
point of this script.
"""
import base64, json, os, re, sys
from urllib.parse import urlparse
from bs4 import BeautifulSoup

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")

# Links we never want in the brief: ads, admin, account, social, legal.
JUNK = re.compile(
    r"doubleclick|^mailto:|unsubscribe|preference-center|customercenter"
    r"|privacy|cookie|/newsletters\?|/newsletters/|help[-_]?centre|helpcentre"
    r"|account|login|log-in|/tips\?|abc\.net\.au/news/newsletters"
    r"|apps\.apple\.com|play\.google\.com|facebook\.com|twitter\.com|x\.com/"
    r"|instagram\.com|youtube\.com|linkedin\.com|/author/|buyside",
    re.I,
)

# Everything from the first match onward is footer furniture. Keyed by the
# leading letters of the slug, because markers are NOT safe across sources:
# "Thanks for reading" ends a Sinocism issue but sits mid-email in ABC AM.
STOP_BY_SOURCE = {
    "abc": ["Sydney 3 day forecast", "Need help?", "Download the app",
            "We acknowledge Aboriginal", "The ABC sent this message"],
    "wsj": ["ABOUT US", "Today's newsletter was curated",
            "Today’s newsletter was curated", "Sign up for WSJ newsletters",
            "You are currently subscribed", "Dow Jones & Company"],
    "sino": ["Thanks for reading", "You're currently a free subscriber",
             "You’re currently a free subscriber", "Get the Sinocism"],
    "bbc": ["You received this email because", "BBC Studios Distribution",
            "Copyright © 2026 BBC"],
}


def stops_for(slug):
    for prefix, markers in STOP_BY_SOURCE.items():
        if slug.startswith(prefix):
            return markers
    return []

INVISIBLE = re.compile(r"[͏​-‏  ­ㅤ﻿᠎]")


def decode_wsj(href):
    """trk.wsj.com/click/NNNN.NNNN/<b64url>/hash -> clean wsj.com URL, or None."""
    m = re.match(r"https://trk\.(?:wsj|dowjones)\.com/click/[\d.]+/([A-Za-z0-9_-]+)/", href)
    if not m:
        return None
    seg = m.group(1)
    try:
        url = base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)).decode("utf-8")
    except Exception:
        return None
    return url if urlparse(url).netloc.endswith("wsj.com") else None


def clean(text, slug):
    text = INVISIBLE.sub("", text)
    for s in stops_for(slug):
        i = text.find(s)
        if i > 400:          # never truncate into the lede
            text = text[:i]
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def main(argv):
    os.makedirs(WORK, exist_ok=True)
    links, bykey, meta = {}, {}, []

    for arg in argv:
        slug, _, path = arg.partition("=")
        d = json.load(open(path))
        body = d.get("plaintextBody") or d.get("htmlBody") or ""

        if d.get("plaintextBody") and not d.get("htmlBody"):
            text, n = clean(body, slug), 0
        else:
            soup = BeautifulSoup(body, "html.parser")
            for t in soup(["style", "script", "head"]):
                t.decompose()
            n = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                label = " ".join(a.get_text(" ", strip=True).split())
                if not label:
                    continue
                target = decode_wsj(href)
                if target is None and "trk.wsj.com" in href:
                    continue                      # ad / undecodable
                target = target or href           # verbatim for everything else
                if JUNK.search(target):
                    continue
                key = bykey.get(target)
                if key is None:
                    n += 1
                    key = f"{slug}_{n}"
                    bykey[target] = key
                    links[key] = target
                a.replace_with(f"{label} [[{key}]]")
            text = clean(soup.get_text("\n", strip=True), slug)

        open(os.path.join(WORK, f"{slug}.txt"), "w").write(text)
        meta.append({"slug": slug, "id": d["id"], "date": d["date"][:10],
                     "subject": d["subject"], "chars": len(text), "links": n})

    json.dump(links, open(os.path.join(WORK, "links.json"), "w"), indent=1)
    for m in meta:
        print(f"{m['slug']:14} id={m['id']} date={m['date']} chars={m['chars']:>6} links={m['links']:>3}")
    print(f"total link keys: {len(links)}")


if __name__ == "__main__":
    main(sys.argv[1:])
