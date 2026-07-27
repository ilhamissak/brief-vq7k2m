# Daily Brief — build pipeline

Static page at <https://ilhamissak.github.io/brief-vq7k2m/>, rebuilt each
morning at 8:40am Sydney by a headless Cowork scheduled task. Runs entirely in
Anthropic's cloud: no laptop, no local machine, no desktop bridge.

## Why the scripts exist

The producer is a language model, and every token it reads is re-sent on every
subsequent turn of the run. So the rule is: **the model reads editorial text and
nothing else.** Raw HTML, tracking URLs, link tables and the design shell never
enter its context. These scripts hold all of that.

## Daily flow

    1  git clone                                    (1 tool call)
    2  ONE Gmail search, then parallel get_message  (2 turns)
    3  python3 build.py slug=path ...               (1 call)
    4  write work/content.json                      (1 write)
    5  ./run.sh '{"id":"date",...}' YYYY-MM-DD      (1 call)

`work/` is gitignored scratch. Only `index.html` and `processed.json` are
committed.

## Scripts

| file | role |
|---|---|
| `build.py` | Gmail JSON → `work/<slug>.txt` (clean text, `[[key]]` markers) + `work/links.json`. Prints counts only. |
| `render.py` | `content.json` + `links.json` + `template.html` → `index.html`. The only place an href is ever written. |
| `check.py` | Link gate. Exits non-zero unless every href came from `build.py`. |
| `publish.py` | Ledger update + prune + commit + push. |
| `run.sh` | render → check → publish, in one shell call. |
| `template.html` | The design shell. Colours and type live here, not in the model's output. |

Slug prefixes matter: `abc`, `wsj`, `sino`, `bbc` select the footer-stripping
rules in `build.py`. A slug that matches none keeps the whole email body.

## Link integrity

ABC and BBC tracking URLs run 400+ characters and break if altered by one
character, so they are carried byte-for-byte from the email and never retyped.
WSJ `trk.wsj.com/click/N.N/<base64>/hash` links are deterministically decoded to
clean `wsj.com` URLs. `check.py` refuses to let anything else through.

## content.json

```jsonc
{
  "date_iso": "2026-07-27",
  "dateline": "Monday 27 July 2026",
  "compiled": "ABC News AM (27 Jul) · ...",     // footer: issues used
  "missing":  "Sinocism (no issue since ...)",  // footer: sources not received
  "sections": [{
    "title":  "Home Front · Australia",
    "empty":  "shown as a card when the section has no stories",   // optional
    "stories": [{
      "k":   "abc_1",          // link key from build.py; headline links here
      "h":   "Headline",
      "s":   "One to three sentences. May contain [[key|anchor]] markers.",
      "src": "ABC News AM · 27 Jul",
      "followup": "Follows 17 Jul: ..."                            // optional
    }],
    "groups": [{               // optional sub-groups of one-line bullets
      "title": "Also today",
      "bullets": ["Text with an [[key|inline link]] in it."]
    }],
    "note": "card at the end of the section"                       // optional
  }]
}
```

Never put a URL in `content.json`. Reference links by key only — `k` for a
headline, `[[key|anchor text]]` inline. `render.py` resolves keys against
`links.json` and aborts on an unknown one.

## Health check

The page footer carries the build timestamp. If it is not today's date, the run
did not happen — the usual causes are the Gmail connector's authorisation
lapsing or the GitHub token expiring, both fixable from phone or web.
