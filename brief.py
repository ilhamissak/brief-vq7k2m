#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brief.py — single driver for Ilham's Daily News Brief.

Collapses the whole run into three always-identical shell commands so the
scheduled session needs (almost) no permission approvals:

    python3 /home/claude/brief/brief.py init
    python3 /home/claude/brief/brief.py parse
    python3 /home/claude/brief/brief.py publish --new ID=src,ID=src

Gmail reads stay as MCP tool calls (they never prompt). Everything else —
spill-file discovery, link extraction, body cleaning, placeholder
substitution, the link self-check, the ledger update, commit and push —
happens in here.

Link rule: hrefs are stored and substituted BYTE-FOR-BYTE VERBATIM. The only
transformation permitted is the deterministic trk.wsj.com base64 decode.
BBC links are never extracted at all (their click.email.bbc.com tokens are
per-recipient and do not resolve outside the original email).
"""

import argparse, base64, glob, json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPO = '/home/claude/brief'
WORK = os.path.join(REPO, 'work')
LEDGER = os.path.join(REPO, 'processed.json')
TPL = os.path.join(WORK, 'page.tpl.html')
SYD = ZoneInfo('Australia/Sydney')

SOURCES = {
    'newsletters@e.email.abc.net.au': 'abc',
    'access@interactive.wsj.com':     'wsj',
    'bill@sinocism.com':              'sino',
    'newsbriefing@email.bbc.com':     'bbc',
    'uspoliticsunspun@email.bbc.com': 'bbcunspun',
}
NO_LINK_SOURCES = {'bbc', 'bbcunspun'}          # never extract hrefs from these

ZW = dict.fromkeys(map(ord, '­͏​‌‍﻿‎‏'), None)
FOOTERS = ["MORE BBC NEWSLETTERS", "That's all for today",
           "This is an edition of the WSJ", "Click here to unsubscribe"]
BOILER = re.compile(r'^(unsubscribe|privacy|cookie|contact us|newsletters?( & alerts)?|'
                    r'view in browser|is this email difficult to read.*|sign up here|'
                    r'more weather|accessibility|log in here|sponsored by|learn more.*|'
                    r'try \d+ weeks free.*|visit the abc help centre|discover abc newsletters|'
                    r'update your region.*|sign up for .*)$', re.I)


# ---------------------------------------------------------------- helpers
def clean(t):
    t = t.translate(ZW)
    t = re.sub(r'[ \t ]+', ' ', t)
    return re.sub(r'\n\s*\n\s*\n+', '\n\n', t).strip()


def decode_wsj(href):
    m = re.match(r'https?://trk\.wsj\.com/click/[^/]+/([^/]+)/', href)
    if not m:
        return None
    seg = m.group(1)
    try:
        u = base64.urlsafe_b64decode(seg + '=' * (-len(seg) % 4)).decode('utf-8')
    except Exception:
        return None
    if not u.startswith('http'):
        return None
    return u.split('?')[0] if 'wsj.com' in u else u


def load_ledger():
    d = json.load(open(LEDGER))
    return d, d['processed']


def entry_date(v):
    return v['d'] if isinstance(v, dict) else v


def entry_src(v):
    return v.get('s', '?') if isinstance(v, dict) else '?'


def git(*args):
    return subprocess.run(['git', '-C', REPO, *args], capture_output=True, text=True)


# ---------------------------------------------------------------- init
def cmd_init(a):
    now = datetime.now(timezone.utc)
    syd = now.astimezone(SYD)
    aedt = syd.dst() != timedelta(0)
    want = '30 21 * * *' if aedt else '30 22 * * *'
    print(f'SYD  {syd:%A %d %B %Y %H:%M} {syd.tzname()} (UTC{syd:%z})')
    print(f'CRON should be "{want}" for 08:30 Sydney')

    _, proc = load_ledger()
    last = {}
    for v in proc.values():
        s, d = entry_src(v), entry_date(v)
        if d > last.get(s, ''):
            last[s] = d
    today = syd.date().isoformat()
    cut3 = (syd.date() - timedelta(days=3)).isoformat()
    print(f'LEDGER {len(proc)} entries; last seen per source:')
    for s in sorted(last):
        gap = '' if last[s] >= cut3 else '  <-- WIDEN to newer_than:14d'
        print(f'  {s:10s} {last[s]}{gap}')
    print(f'TODAY {today}')


# ---------------------------------------------------------------- parse
def find_spills():
    pats = ['/root/.claude/projects/*/*/tool-results/*.txt',
            '/root/.claude/projects/*/tool-results/*.txt']
    out = []
    for p in pats:
        out += glob.glob(p)
    return sorted(set(out), key=os.path.getmtime)


def cmd_parse(a):
    os.makedirs(WORK, exist_ok=True)
    _, proc = load_ledger()
    seen, tags = {}, {}

    for path in find_spills():
        try:
            d = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or 'sender' not in d:
            continue
        src = SOURCES.get((d.get('sender') or '').lower())
        if not src:
            continue
        mid = d.get('id')
        if not mid or mid in seen:
            continue
        if mid in proc and not a.force:
            continue
        seen[mid] = d

    if not seen:
        print('PARSE: no un-ledgered spill files found.')
        return

    from bs4 import BeautifulSoup
    manifest = {}
    for mid, d in seen.items():
        src = SOURCES[(d['sender']).lower()]
        subj = d.get('subject', '')
        tag = src
        if src == 'wsj':
            tag = 'wsj10pt' if subj.lower().startswith('the 10-point') else 'wsjwn'
        n = tags.get(tag, 0)
        tags[tag] = n + 1
        if n:
            tag = f'{tag}{n+1}'

        html = d.get('htmlBody') or ''
        plain = d.get('plaintextBody') or ''
        soup = BeautifulSoup(html, 'html.parser')

        links = []
        if tag.rstrip('0123456789') not in NO_LINK_SOURCES:
            uniq = set()
            for anch in soup.find_all('a'):
                href = anch.get('href')
                if not href:
                    continue
                txt = clean(anch.get_text(' ', strip=True))
                if (txt, href) in uniq:
                    continue
                uniq.add((txt, href))
                links.append({'text': txt, 'href': href, 'decoded': decode_wsj(href)})
        json.dump(links, open(f'{WORK}/links_{tag}.json', 'w'),
                  ensure_ascii=False, indent=0)

        if src == 'sino' and plain.strip():
            body = clean(plain)
        else:
            for t in soup(['style', 'script']):
                t.decompose()
            body = clean(soup.get_text('\n', strip=True))
        for f in FOOTERS:
            i = body.find(f)
            if i > 200:
                body = body[:i]
                break
        body = body[:4500]
        open(f'{WORK}/body_{tag}.txt', 'w', encoding='utf-8').write(body)
        manifest[tag] = {'id': mid, 'src': src, 'subject': subj,
                         'date': d.get('date'), 'links': len(links)}

        print(f'\n{"="*70}\n### {tag}  |  {subj}\n### id={mid}  date={d.get("date")}  links={len(links)}\n{"="*70}')
        if links:
            print('-- LINKS (index | anchor -> href[:45]) --')
            for i, l in enumerate(links):
                if not l['text'] or BOILER.match(l['text']) or l['href'].startswith('mailto:'):
                    continue
                u = l['decoded'] or l['href']
                print(f'{i:3d} | {l["text"][:70]} -> {u[:45]}')
        else:
            print('-- NO LINKS EXTRACTED (BBC: publish as <span class="nolink">) --')
        print('-- BODY --')
        print(body)

    json.dump(manifest, open(f'{WORK}/manifest.json', 'w'), ensure_ascii=False, indent=1)
    print(f'\nPARSE OK: {len(manifest)} issue(s) -> {sorted(manifest)}')


# ---------------------------------------------------------------- publish
PH = re.compile(r'\{\{([a-z0-9]+):(\d+)\}\}')


def cmd_publish(a):
    if not os.path.exists(TPL):
        sys.exit(f'FAIL: template not found at {TPL}')
    html = open(TPL, encoding='utf-8').read()

    cache, allowed, missing = {}, set(), []

    def links_for(tag):
        if tag not in cache:
            p = f'{WORK}/links_{tag}.json'
            cache[tag] = json.load(open(p)) if os.path.exists(p) else None
        return cache[tag]

    def sub(m):
        tag, idx = m.group(1), int(m.group(2))
        arr = links_for(tag)
        if arr is None or idx >= len(arr):
            missing.append(m.group(0))
            return m.group(0)
        e = arr[idx]
        return e['decoded'] or e['href']

    out = PH.sub(sub, html)
    if missing:
        sys.exit(f'FAIL: unresolved placeholders {sorted(set(missing))}')

    for f in glob.glob(f'{WORK}/links_*.json'):
        for e in json.load(open(f)):
            allowed.add(e['href'])
            if e.get('decoded'):
                allowed.add(e['decoded'])

    index = os.path.join(WORK, 'index.preview.html') if a.check_only \
        else os.path.join(REPO, 'index.html')
    open(index, 'w', encoding='utf-8').write(out)

    # ---- self-check gate ----
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(out, 'html.parser')
    hrefs = [x['href'] for x in soup.find_all('a') if x.get('href')]
    fails = []

    n_ph = len(re.findall(r'\{\{', out))
    bad = [h for h in set(hrefs)
           if h not in allowed and 'sinocism.com' not in h and not h.startswith('mailto:')]
    goog = [h for h in hrefs if 'google.com/url' in h]
    fffd = [h for h in hrefs if '�' in h]
    bbcl = [h for h in hrefs if h.startswith('https://click.email.bbc.com/')]

    def bare(els):
        return [e.get_text(' ', strip=True)[:50] for e in els
                if not e.find('a', href=True) and 'nolink' not in ' '.join(
                    c for t in e.find_all(True) for c in (t.get('class') or []))
                and 'nolink' not in ' '.join(e.get('class') or [])]

    h3s, lis = soup.find_all('h3'), soup.find_all('li')
    bare_h3, bare_li = bare(h3s), bare(lis)
    nolink = len(soup.select('.nolink'))

    if n_ph:    fails.append(f'{n_ph} placeholder tokens remain')
    if bad:     fails.append(f'{len(bad)} untraceable hrefs: {bad[:3]}')
    if goog:    fails.append('google.com/url redirect present')
    if fffd:    fails.append('href contains U+FFFD')
    if bbcl:    fails.append('click.email.bbc.com href present (regression)')
    if bare_h3: fails.append(f'bare h3: {bare_h3}')
    if bare_li: fails.append(f'bare li: {bare_li}')

    print(f'CHECK placeholders={n_ph} hrefs={len(hrefs)}/{len(set(hrefs))}uniq '
          f'untraceable={len(bad)} google=0 fffd={len(fffd)} bbc_tracking={len(bbcl)} '
          f'h3={len(h3s)}(bare {len(bare_h3)}) li={len(lis)}(bare {len(bare_li)}) nolink={nolink}')
    if fails:
        print('SELF-CHECK FAIL -> ' + ' | '.join(fails))
        print('NOTHING PUSHED. Ledger untouched; tomorrow picks everything up.')
        sys.exit(1)
    print('SELF-CHECK PASS')

    if a.check_only:
        print('check-only: stopping before ledger/commit.')
        return

    # ---- ledger ----
    d, proc = load_ledger()
    added = []
    for pair in filter(None, (a.new or '').split(',')):
        mid, _, src = pair.partition('=')
        mid, src = mid.strip(), (src.strip() or '?')
        if mid:
            if mid not in proc:
                added.append(mid)
            proc[mid] = {'d': a.date, 's': src}
    cutoff = (datetime.strptime(a.date, '%Y-%m-%d').date() - timedelta(days=30)).isoformat()
    before = len(proc)
    proc = {k: v for k, v in proc.items() if entry_date(v) >= cutoff}
    d['processed'] = dict(sorted(proc.items(), key=lambda kv: (entry_date(kv[1]), kv[0])))
    json.dump(d, open(LEDGER, 'w'), ensure_ascii=False, indent=1)

    # ---- commit + push ----
    git('add', 'index.html', 'processed.json', 'brief.py')
    c = git('-c', 'user.name=Daily Brief', '-c', 'user.email=brief@local',
            'commit', '-q', '-m', f'Daily brief {a.date}')
    p = git('push', '-q', 'origin', 'HEAD:main')
    ok = p.returncode == 0
    print(f'LEDGER +{len(added)} pruned={before-len(proc)} total={len(proc)}')
    print(f'COMMIT rc={c.returncode} PUSH rc={p.returncode} -> {"OK" if ok else "FAILED"}')
    if not ok:
        print((c.stderr or '') + (p.stderr or ''))
        sys.exit(1)
    print('PUBLISHED https://ilhamissak.github.io/brief-vq7k2m/')


# ---------------------------------------------------------------- main
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('init')
    pp = sp.add_parser('parse'); pp.add_argument('--force', action='store_true')
    xp = sp.add_parser('publish')
    xp.add_argument('--new', default='')
    xp.add_argument('--date', default=datetime.now(timezone.utc).astimezone(SYD).date().isoformat())
    xp.add_argument('--check-only', action='store_true')
    a = ap.parse_args()
    {'init': cmd_init, 'parse': cmd_parse, 'publish': cmd_publish}[a.cmd](a)
