# Outreach pipeline

Sources AI-infrastructure companies, finds their *publicly published* contact
addresses, and drafts one cold email per company in Srija's voice — then stops,
so a human sends.

```
targets.yaml  ──►  scrape.py  ──►  out/contacts.json  ──►  compose.py  ──►  out/drafts.json  ──►  review, then send
   curated          discover            verified              draft +              ready to
   companies        addresses           addresses             validate             paste
```

## Why it is built this way

**It does not guess addresses.** A permutation pipeline (`first@`, `careers@`,
`f.last@`) generates bounces, and bounces are what get a personal Gmail account
flagged as a spam sender. `scrape.py` only accepts an address that literally
appears on one of the company's own pages, and records which page it came from.

**It does not invent reasons to be interested.** Every email opens with one
verifiable fact about the company, taken from the `note` field. If a target has
no `note`, `compose.py` blocks the draft rather than padding it with a
compliment. That is the `BLOCKED ... refusing to invent a hook` case.

**It separates role inboxes from people.** Addresses like `hello@` or `careers@`
are auto-usable. Anything that looks like a named individual goes into
`manual_review` for a human to decide on.

**It is polite to the sites it reads.** robots.txt is honoured, requests are
serialised with a delay, and the User-Agent says who is asking and why.

**It never sends.** The pipeline's last output is a JSON file. Sending is a
separate, human-initiated step.

## Run it

```bash
pip install pyyaml

# 1. discover published contact addresses (see network note below)
python outreach/scrape.py --max-priority 1 --delay 1.5

# 2. draft and validate
python outreach/compose.py --contacts outreach/out/contacts.json \
                           --comp-stance flexible

# Addresses already verified by hand live in targets.yaml, so you can skip
# step 1 entirely and compose straight from it:
python outreach/compose.py --contacts outreach/targets.yaml
```

`--comp-stance` picks how the internship ask is framed:

| value       | line used                                                    |
|-------------|--------------------------------------------------------------|
| `flexible`  | "I am flexible on comp and hours if the work is real." (default) |
| `unpaid_ok` | "Paid or unpaid both work for me."                           |
| `paid_only` | "...looking for a paid internship."                          |

## Rules the composer enforces

`compose.py` encodes the hard rules from the `srija-cold-email` skill as a
validator, and refuses to emit a draft that breaks one:

1. No mention of work authorization, visa, sponsorship, or citizenship — in any
   form, including as a positive.
2. The signature is exactly name + phone + email. No links, no title stack.
3. Body is 90–150 words.
4. No filler openers ("I hope this email finds you well", "I am reaching out",
   "passionate about", "leverage", "please let me know if there are any
   opportunities").
5. The opening line comes from a verified fact, or the draft is blocked.

Every claim in `ANGLES` traces to her career facts. Adding a new angle means
adding a fact she can defend in the interview that follows.

## Network note

`scrape.py` needs direct outbound HTTPS to the target domains. It returns
`NOT FOUND` for everything when run from a sandbox whose egress policy only
allows an allowlist — that is the environment refusing `CONNECT`, not the
companies having no contact page. Check with:

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"   # look for connect_rejected entries
```

Run it from an unrestricted machine, or paste addresses into `targets.yaml` by
hand as the tier-1 entries already are.

## State of the target list (researched 2026-09-17)

This market consolidated hard in 2026, which matters because an internship
pitch to an acquired team is wasted effort:

- **ClickHouse acquired Langfuse** (Jan 16) — still shipping as a distinct
  product, Langfuse Gateway on the roadmap. Still worth writing to.
- **Mintlify acquired Helicone** (Mar 3) — platform in maintenance mode,
  feature development ended. Marked `SKIP`.
- **Palo Alto Networks acquired Portkey** (closed May 29) — now ships as Prisma
  AIRS AI Gateway. Marked `SKIP` as a *startup* target; their internship
  programme is a large-company application, not a cold email.

Of the 17 targets, 3 have a verified published address. Most of the rest hire
through Ashby or Greenhouse boards and publish no address at all, which is the
honest state of this space: **for most of them, applying to a posted role beats
cold email.** The `channel` field on each target records which it is.
