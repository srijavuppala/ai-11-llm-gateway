"""Compose Srija's outreach emails and validate them against her own rules.

The srija-cold-email skill has hard rules. Rather than trusting each draft to
respect them, they are encoded as a validator here and every draft is checked
before it can be written out. A draft that fails is not emitted.

Rules enforced:
  1. No mention of work authorization, visa, sponsorship, or citizenship.
  2. Signature is exactly name + phone + email. No links, no title stack.
  3. Body is 90-150 words.
  4. No filler openers ("I hope this email finds you well", "I am reaching out").
  5. The "why them" line must come from a verified fact about the company.
     If there is no such fact, the draft is rejected rather than padded with a
     fabricated compliment.
"""

from __future__ import annotations

import argparse
import json
import re

NAME = "Srija Vuppala"
PHONE = "+1 (469) 213-9938"
EMAIL = "srijavuppala11@gmail.com"
SIGNATURE = f"{NAME}\n{PHONE} | {EMAIL}"

# Rule 1. Never, in any form, including as a positive.
BANNED_AUTHORIZATION = re.compile(
    r"\b(work auth\w*|authorized to work|authorisation|visa|sponsor\w*|green card|"
    r"citizen\w*|permanent resident|opt\b|cpt\b|h-?1b|f-?1\b|ead\b|stem opt)\b",
    re.I,
)

# Rule 4. Filler that makes a cold email read like every other cold email.
BANNED_FILLER = [
    "i hope this email finds you well",
    "i hope you are doing well",
    "i am reaching out",
    "i'm reaching out",
    "passionate about",
    "leverage",
    "synergies",
    "please let me know if there are any opportunities",
    "to whom it may concern",
    "dear sir or madam",
    "any opportunity would be greatly appreciated",
    "i would be grateful",
    "humbly request",
]

# Per-category angle. Every claim traces to her career facts; nothing invented.
ANGLES = {
    "gateway": {
        "ask": "Worth 15 minutes? I can also just send a short walkthrough of how it handles provider failover.",
        "subject": "LLM gateway at 25k users",
        "bridge": (
            "I built the same thing you sell. At UT Dallas I built and ran Comet AI, a "
            "production gateway that put multiple LLM providers behind one interface "
            "for 25,000+ users, and owned its deployment, access management and "
            "reliability."
        ),
        "extra": (
            "I also have a merged PR in BerriAI/litellm, hardening its safe_json_dumps "
            "utility with tests through full CI and maintainer review."
        ),
    },
    "devtools_oss": {
        "ask": "Worth 15 minutes? Happy to pick up an issue off your tracker in the meantime.",
        "subject": "merged PR, internship ask",
        "bridge": (
            "I have a merged PR in your repo. I hardened safe_json_dumps against failing "
            "custom __str__ methods and non-string keys, which was crashing "
            "serialization in the request-logging path, added unit tests, and took it "
            "through maintainer review, Ruff and Codecov into an upstream release."
        ),
        "extra": (
            "I ran the other side of that too: Comet AI at UT Dallas, a platform "
            "unifying multiple LLM providers for 25,000+ users, where I owned "
            "deployment, guardrails and incident response."
        ),
    },
    "observability": {
        "ask": "Worth 15 minutes? I can also send a note on what those dashboards caught and what they missed.",
        "subject": "tracing LLM traffic at 25k users",
        "bridge": (
            "I ran the thing you instrument. Comet AI at UT Dallas served 25,000+ users "
            "across multiple LLM providers, and I owned its reliability end to end: "
            "load testing, CI/CD, Splunk dashboards, and automated alerting and "
            "incident triggering across sandbox and production."
        ),
        "extra": (
            "I also built a multi-agent research system on the OpenAI Agents SDK with full "
            "tracing of every agent decision, so I know what is missing when an agent "
            "loop goes wrong."
        ),
    },
    "evals": {
        "ask": "Worth 15 minutes? I can also just send the eval pipeline setup.",
        "subject": "guardrail evals, internship ask",
        "bridge": (
            "Evaluating guardrails was most of my last job. On Comet AI at UT Dallas "
            "(25,000+ users) I built multi-model evaluation pipelines and applied QLoRA "
            "fine-tuning to stress-test guardrails, content filtering, off-topic "
            "rejection and policy-violation detection, which improved compliance "
            "detection and cut false-positive rejections."
        ),
        "extra": (
            "Its RAG support agent deflected about 40% of Tier-2 IT tickets, with "
            "responses kept inside policy."
        ),
    },
    "agent_infra": {
        "ask": "Worth 15 minutes? I can also just send a short walkthrough of the MCP server.",
        "subject": "MCP server, internship ask",
        "bridge": (
            "I build on this layer. I wrote a Python FastMCP server exposing Icarus Verilog, "
            "Verilator and Yosys as callable tools so coding agents can generate, simulate "
            "and synthesize RTL."
        ),
        "extra": (
            "I also built MEMO, a document-grounded LangGraph ReAct agent that extracts "
            "atomic facts into a knowledge graph and detects cross-document "
            "contradictions with an NLI cross-encoder, so every answer traces back to "
            "a source instead of drifting as the context fills."
        ),
    },
    "finetuning": {
        "ask": "Worth 15 minutes? I can also just send the QLoRA evaluation setup.",
        "subject": "QLoRA guardrail evals",
        "bridge": (
            "I have used QLoRA on production work, not just notebooks. On Comet AI at UT "
            "Dallas (25,000+ users) I applied QLoRA fine-tuning and multi-model "
            "evaluation pipelines to stress-test guardrails and policy-violation "
            "detection."
        ),
        "extra": (
            "That work improved compliance detection and cut false-positive rejections, "
            "and I owned the platform's deployment and reliability alongside it."
        ),
    },
    "infra": {
        "ask": "Worth 15 minutes? I can also just send the load-test and alerting setup.",
        "subject": "reliability at 25k users",
        "bridge": (
            "I kept inference up for real users. I built and ran Comet AI at UT Dallas, a "
            "multi-provider LLM platform serving 25,000+ users, including load testing, "
            "CI/CD, Splunk observability dashboards, and alerting across sandbox and "
            "production."
        ),
        "extra": (
            "Before that I built healthcare data pipelines and CI/CD automation on AWS at "
            "Optum."
        ),
    },
}

# She finished the M.S. in May 2026 and can start immediately. She cannot
# relocate, so "remote" is stated up front instead of surfacing on the call.
AVAILABILITY = "I finished my M.S. at UT Dallas in May and can start now, remote."

COMP_LINES = {
    # Honest framing that does not undersell her. Recommended default.
    "flexible": (
        f"{AVAILABILITY} I am flexible on comp and hours if the work is real."
    ),
    # Explicit, if she wants to remove any budget friction.
    "unpaid_ok": (
        f"{AVAILABILITY} Paid or unpaid both work for me. I care more about "
        "shipping something real."
    ),
    "paid_only": f"{AVAILABILITY} I am looking for something paid.",
}

ASK = "Worth a 15-minute call? I can also just send a short walkthrough of the gateway."


def compose(target: dict, comp_stance: str = "flexible") -> dict:
    """Build one email. Returns a dict with the draft plus any rule violations."""
    category = target.get("category", "infra")
    angle = ANGLES.get(category, ANGLES["infra"])
    note = (target.get("note") or "").strip()
    company = target["name"]
    short = target.get("short_name") or company
    recipient = (target.get("recipient") or "").strip()
    greeting = f"Hi {recipient}," if recipient else f"Hi {short} team,"

    problems: list[str] = []

    # Rule 5: no verified fact about them means no email.
    if not note:
        problems.append("no verified fact about this company; refusing to invent a hook")
        why_them = ""
    else:
        why_them = f"You {note}."

    body = "\n\n".join([
        greeting,
        why_them,
        angle["bridge"],
        angle["extra"],
        COMP_LINES[comp_stance],
        angle.get("ask", ASK),
        SIGNATURE,
    ])

    subject = f"{short} — {angle['subject']}"
    problems.extend(validate(subject, body))

    return {
        "company": company,
        "short_name": short,
        "recipient": recipient,
        "domain": target.get("domain"),
        "to": target.get("contact"),
        "category": category,
        "priority": target.get("priority", 2),
        "subject": subject,
        "body": body,
        "word_count": _word_count(body),
        "problems": problems,
        "ready": not problems and bool(target.get("contact")),
    }


def _word_count(body: str) -> int:
    """Words in the pitch, excluding greeting and signature."""
    lines = [ln for ln in body.split("\n\n")]
    pitch = " ".join(lines[1:-1]) if len(lines) > 2 else body
    return len(pitch.split())


def validate(subject: str, body: str) -> list[str]:
    problems: list[str] = []
    low = body.lower()

    if BANNED_AUTHORIZATION.search(body) or BANNED_AUTHORIZATION.search(subject):
        problems.append("mentions work authorization / visa / sponsorship")

    for phrase in BANNED_FILLER:
        if phrase in low:
            problems.append(f"filler phrase: {phrase!r}")

    if not body.rstrip().endswith(SIGNATURE):
        problems.append("signature is not the exact required block")

    # No links in the signature block, and no stray profile links anywhere.
    if re.search(r"(linkedin\.com|github\.com|https?://)", body, re.I):
        problems.append("contains a link; signature must be name + phone + email only")

    wc = _word_count(body)
    if not 90 <= wc <= 150:
        problems.append(f"body is {wc} words, outside the 90-150 range")

    words = len(subject.split())
    if words > 9:
        problems.append(f"subject is {words} words, too long")

    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contacts", default="outreach/out/contacts.json")
    ap.add_argument("--out", default="outreach/out/drafts.json")
    ap.add_argument("--comp-stance", choices=sorted(COMP_LINES), default="flexible")
    ap.add_argument("--max-priority", type=int, default=3)
    args = ap.parse_args()

    with open(args.contacts) as fh:
        if args.contacts.endswith((".yaml", ".yml")):
            # Compose straight from targets.yaml when the addresses in it are
            # already verified, skipping the scrape step.
            import yaml
            contacts = yaml.safe_load(fh)["targets"]
        else:
            contacts = json.load(fh)

    drafts = [
        compose(c, comp_stance=args.comp_stance)
        for c in contacts
        if int(c.get("priority", 2)) <= args.max_priority
    ]

    with open(args.out, "w") as fh:
        json.dump(drafts, fh, indent=2)

    ready = [d for d in drafts if d["ready"]]
    print(f"{len(ready)}/{len(drafts)} drafts ready -> {args.out}")
    for d in drafts:
        if d["ready"]:
            print(f"  OK       {d['short_name']:<14} {d['to']:<24} ({d['word_count']}w)")
            print(f"           subj: {d['subject']}")
    for d in drafts:
        if not d["ready"]:
            reason = "; ".join(d["problems"]) or "no verified contact address"
            print(f"  BLOCKED  {d['short_name']:<14} {reason}")


if __name__ == "__main__":
    main()
