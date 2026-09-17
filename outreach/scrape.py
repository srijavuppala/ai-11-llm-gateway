"""Discover publicly published contact addresses for the target companies.

Deliberate constraints, because this sends mail to real people:

* Only pages the site itself publishes are read (home, /contact, /careers, ...).
* robots.txt is honoured. A disallowed path is skipped, not fetched.
* Addresses are never *guessed*. "careers@<domain>" is only used if that exact
  string appears on one of their own pages. A permuted-guess pipeline would
  produce bounces and land her in spam filters, which is the opposite of useful.
* Role addresses (careers@, hello@, ...) are auto-usable. Anything that looks
  like a named individual is surfaced for manual review instead, so she decides
  whether writing to a person's direct address is appropriate.
* One request at a time with a delay, and a User-Agent that says who this is.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field

import yaml

UA = (
    "SrijaVuppala-JobOutreach/1.0 "
    "(individual job seeker researching contact addresses; "
    "srijavuppala11@gmail.com)"
)

# Paths a company typically publishes contact details on.
CANDIDATE_PATHS = ["/", "/contact", "/contact-us", "/careers", "/jobs", "/about", "/company"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses that belong to a function rather than a person.
ROLE_LOCALPARTS = {
    "careers", "jobs", "hiring", "recruiting", "recruitment", "talent",
    "hello", "hi", "hey", "team", "founders", "info", "contact", "support",
    "sales", "press", "help", "admin", "people", "work", "join",
}

# Addresses that are never outreach targets.
JUNK_LOCALPARTS = {"noreply", "no-reply", "donotreply", "postmaster", "abuse",
                   "security", "privacy", "legal", "dmca", "unsubscribe", "bounce"}

JUNK_DOMAIN_HINTS = ("sentry.io", "example.com", "domain.com", "yourcompany.com",
                     "wixpress.com", "sentry-next.wixpress.com")


@dataclass
class ScrapeResult:
    name: str
    domain: str
    category: str
    priority: int
    note: str
    contact: str | None = None            # auto-usable role address
    contact_source: str | None = None     # the page it was found on
    manual_review: list[str] = field(default_factory=list)  # named individuals
    hook_text: str | None = None          # real copy from their site
    errors: list[str] = field(default_factory=list)


def _get(url: str, timeout: float = 15.0) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return None
            return resp.read(1_500_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def _robots(domain: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"https://{domain}/robots.txt")
    try:
        rp.read()
    except Exception:
        # No reachable robots.txt: treat as unrestricted, which is the
        # standard interpretation.
        rp.parse(["User-agent: *", "Allow: /"])
    return rp


def _classify(addr: str, domain: str) -> str:
    """Return 'role', 'person', or 'junk'."""
    addr = addr.lower().strip(".,;:()<>\"'")
    local, _, host = addr.partition("@")
    if any(h in host for h in JUNK_DOMAIN_HINTS):
        return "junk"
    if local in JUNK_LOCALPARTS:
        return "junk"
    # Only keep addresses on the company's own domain; a Gmail address scraped
    # off a blog post is not a company contact channel.
    root = ".".join(domain.split(".")[-2:])
    if not host.endswith(root):
        return "junk"
    if local in ROLE_LOCALPARTS:
        return "role"
    return "person"


def _extract_hook(html: str) -> str | None:
    """Pull the site's own one-line description, so the email cites real copy."""
    for pat in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{25,300})["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{25,300})["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            text = re.sub(r"\s+", " ", m.group(1)).strip()
            if text:
                return text
    return None


def scrape(target: dict, delay: float = 1.5) -> ScrapeResult:
    domain = target["domain"]
    res = ScrapeResult(
        name=target["name"],
        domain=domain,
        category=target.get("category", "infra"),
        priority=int(target.get("priority", 2)),
        note=target.get("note", "") or "",
    )

    rp = _robots(domain)
    seen_person: set[str] = set()

    for path in CANDIDATE_PATHS:
        url = f"https://{domain}{path}"
        if not rp.can_fetch(UA, url):
            res.errors.append(f"robots.txt disallows {path}")
            continue

        html = _get(url)
        time.sleep(delay)
        if not html:
            continue

        if res.hook_text is None and path == "/":
            res.hook_text = _extract_hook(html)

        # mailto: links are the strongest signal - the site is explicitly
        # publishing that address as a contact channel.
        found: list[str] = []
        for m in re.finditer(r'mailto:([^"\'?>\s]+)', html, re.I):
            found.append(urllib.parse.unquote(m.group(1)))
        found.extend(EMAIL_RE.findall(html))

        for raw in found:
            addr = raw.lower().strip(".,;:()<>\"'")
            kind = _classify(addr, domain)
            if kind == "junk":
                continue
            if kind == "role":
                if res.contact is None:
                    res.contact = addr
                    res.contact_source = url
            elif addr not in seen_person:
                seen_person.add(addr)
                res.manual_review.append(f"{addr} (found on {url})")

        if res.contact:
            break  # good enough; stop hitting their server

    if not res.contact and not res.manual_review:
        res.errors.append("no published contact address found on public pages")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", default="outreach/targets.yaml")
    ap.add_argument("--out", default="outreach/out/contacts.json")
    ap.add_argument("--max-priority", type=int, default=3,
                    help="skip targets with priority above this")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="seconds between requests")
    ap.add_argument("--only", default=None,
                    help="comma-separated substrings; only scrape matching companies")
    args = ap.parse_args()

    with open(args.targets) as fh:
        targets = yaml.safe_load(fh)["targets"]

    if args.only:
        wanted = [s.strip().lower() for s in args.only.split(",") if s.strip()]
        targets = [t for t in targets
                   if any(w in t["name"].lower() or w in t["domain"].lower() for w in wanted)]

    targets = [t for t in targets if int(t.get("priority", 2)) <= args.max_priority]

    results = []
    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {t['name']} ({t['domain']})", flush=True)
        r = scrape(t, delay=args.delay)
        status = r.contact or (f"{len(r.manual_review)} personal addr(s), manual review"
                               if r.manual_review else "NOT FOUND")
        print(f"          -> {status}", flush=True)
        results.append(asdict(r))

    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2)

    auto = sum(1 for r in results if r["contact"])
    print(f"\n{auto}/{len(results)} have an auto-usable role address -> {args.out}")


if __name__ == "__main__":
    main()
