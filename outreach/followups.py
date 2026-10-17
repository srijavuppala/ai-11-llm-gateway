"""Day-4 and day-10 follow-ups for an outreach email that got no reply.

Two rules make the difference between a follow-up and a nag:

* Each one carries something the first email did not. "Just bumping this" asks
  the recipient to do work and gives them nothing, so it gets ignored twice.
* The last one gives them an out, and converts a no into something smaller they
  can say yes to. A founder who will not hire an intern will often still point
  at an issue worth picking up.

Same hard rules as compose.py: no work-authorization mention, exact signature,
no links unless Srija asks for them in a specific send.
"""

from __future__ import annotations

import argparse
import json

from compose import SIGNATURE, validate

# Follow-ups are short, so the 90-150 word floor in compose.validate does not
# apply. Everything else does.
MIN_WORDS, MAX_WORDS = 35, 95


FOLLOWUPS = {
    "devtools_oss": {
        "day4": (
            "One thing I should have put in the first note: separately from the "
            "platform work, I built my own gateway, with per-team auth, request "
            "rate limits, monthly budget caps, model allowlists, and provider "
            "fallback behind circuit breakers.\n\n"
            "Glad to send it over, or to just take an issue off the tracker as a "
            "trial run. No commitment either way."
        ),
        "day10": (
            "Last note from me, so I am not cluttering your inbox.\n\n"
            "If an internship is not on the table, I would still like to keep "
            "contributing to litellm. If there is an area you want covered, tell me "
            "which one and I will pick it up."
        ),
    },
    "gateway": {
        "day4": (
            "Worth adding to the note below: I also built my own gateway, with "
            "per-team auth, rate limits, monthly budget caps, model allowlists and "
            "provider fallback behind circuit breakers. It is the same shape as "
            "what you ship, at a much smaller scale.\n\n"
            "Happy to send it over if that is a more useful signal than a call."
        ),
        "day10": (
            "Last note from me on this.\n\n"
            "If there is no internship to talk about, that is fine. If it would help "
            "to see how I work first, point me at something and I will do it and "
            "send it back."
        ),
    },
    "observability": {
        "day4": (
            "One thing I left out: the part I found hardest at 25,000 users was not "
            "collecting traces, it was deciding what deserved an alert. Most of what "
            "we caught early came from a handful of hand-built dashboards, not from "
            "the default instrumentation.\n\n"
            "Happy to write that up properly if it is useful."
        ),
        "day10": (
            "Last note from me, so I am not filling your inbox.\n\n"
            "If there is nothing open, no problem. If it would help to see how I work "
            "first, point me at something small and I will do it and send it back."
        ),
    },
    "agent_infra": {
        "day4": (
            "One thing I should have added: the MCP server I wrote exposes three real "
            "toolchains to an agent, so I have spent a while on the unglamorous part, "
            "which is what happens when a tool call fails halfway and the agent has "
            "to recover rather than retry blindly.\n\n"
            "Happy to send a short walkthrough."
        ),
        "day10": (
            "Last note from me on this.\n\n"
            "If there is nothing open right now, that is fine. If you would rather see "
            "work than a CV, point me at something small and I will do it and send it "
            "back."
        ),
    },
}

# Used for any category without its own entry.
GENERIC = FOLLOWUPS["gateway"]


def build(draft: dict, which: str) -> dict:
    """Build one follow-up as a reply on the original thread."""
    category = draft.get("category", "gateway")
    text = FOLLOWUPS.get(category, GENERIC)[which]
    recipient = draft.get("recipient") or ""
    greeting = f"Hi {recipient}," if recipient else f"Hi {draft['short_name']} team,"

    body = f"{greeting}\n\n{text}\n\n{SIGNATURE}"

    # Reuse the shared validator, then re-check length against this file's range.
    problems = [p for p in validate(f"Re: {draft['subject']}", body)
                if "words, outside" not in p]
    words = len(" ".join(body.split("\n\n")[1:-1]).split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"follow-up is {words} words, outside {MIN_WORDS}-{MAX_WORDS}")

    return {
        "company": draft["company"],
        "short_name": draft["short_name"],
        "to": draft["to"],
        "subject": f"Re: {draft['subject']}",
        "body": body,
        "which": which,
        "word_count": words,
        "problems": problems,
        "ready": not problems,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drafts", default="outreach/out/drafts.json")
    ap.add_argument("--out", default="outreach/out/followups.json")
    ap.add_argument("--only", default=None, help="comma-separated short names")
    args = ap.parse_args()

    with open(args.drafts) as fh:
        drafts = [d for d in json.load(fh) if d["ready"]]

    if args.only:
        want = {s.strip().lower() for s in args.only.split(",")}
        drafts = [d for d in drafts if d["short_name"].lower() in want]

    out = [build(d, which) for d in drafts for which in ("day4", "day10")]

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"{sum(1 for f in out if f['ready'])}/{len(out)} follow-ups ready -> {args.out}")
    for f in out:
        state = "OK     " if f["ready"] else "BLOCKED"
        print(f"  {state} {f['short_name']:<12} {f['which']:<6} {f['word_count']:>3}w "
              f"{'; '.join(f['problems'])}")


if __name__ == "__main__":
    main()
