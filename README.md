# 🔀 Project 11 — LLM Gateway with Rate Limiting and Fallback

A production API gateway that sits between your teams and LLM providers. Handles per-team authentication, rate limits, monthly budget enforcement, model allowlists, and automatic provider fallback with circuit breakers. All teams point at the gateway instead of OpenAI directly — one config file controls everything.

---

## Architecture

```
Team A App          Team B App          Team C App
     │                   │                   │
     │  X-Team-ID + Bearer token             │
     └───────────────────┴───────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │        LLM Gateway (main.py)        │
        │                                    │
        │  1. Auth: verify API key + team    │
        │  2. Rate limit: req/min per team   │
        │  3. Budget: monthly $ cap          │
        │  4. Allowlist: model permitted?    │
        │  5. Circuit breaker: provider up?  │
        │  6. Route to provider              │
        │     (OpenAI → Anthropic fallback)  │
        │  7. Log: team, model, cost, ms     │
        └─────────────┬──────────────────────┘
                      │
           ┌──────────┴──────────┐
           ▼                     ▼
       OpenAI API         Anthropic API
       (primary)          (fallback)
```

---

## Features

**Per-team API keys** — each team gets their own key. Gateway verifies both the key and the `X-Team-ID` header. Revoke a team's access by removing one line from `config/teams.yaml`.

**Rate limiting** in `rate_limiter.py` — sliding window counter per team stored in SQLite. Configurable requests-per-minute per team.

**Monthly budget enforcement** — tracks cumulative spend per team in SQLite. Requests are rejected with HTTP 402 when the team's monthly budget is exhausted.

**Model allowlists** — each team can be restricted to specific models. Engineering team gets GPT-4o; the free tier only gets GPT-4o-mini.

**Provider fallback** — on `RateLimitError` or `APIError` from the primary provider, automatically retries on the next configured provider. Adds `x-fallback: true` header to the response.

**Admin dashboard** in `dashboard.py` — per-team spend vs budget, request volume, top models, and request log.

---

## Setup

```bash
cd 11-llm-gateway
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add:
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-... (for fallback)
```

Edit `config/teams.yaml`:
```yaml
teams:
  engineering:
    api_key: "eng-secret-key-abc123"
    monthly_budget_usd: 100
    rate_limit_rpm: 60
    allowed_models: ["gpt-4o", "gpt-4o-mini"]
    providers: ["openai", "anthropic"]

  data-team:
    api_key: "data-secret-key-xyz789"
    monthly_budget_usd: 20
    rate_limit_rpm: 20
    allowed_models: ["gpt-4o-mini"]
    providers: ["openai"]
```

---

## How to Run

### Start the gateway

```bash
python src/main.py
# Gateway at http://localhost:8000
```

### Send a request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer eng-secret-key-abc123" \
  -H "X-Team-ID: engineering" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]}'
```

Response includes routing metadata:
```json
{
  "choices": [...],
  "x_team": "engineering",
  "x_provider": "openai",
  "x_fallback": false
}
```

### Check team stats

```bash
curl http://localhost:8000/admin/teams
# Returns spend, request count, avg latency per team
```

### Launch admin dashboard

```bash
streamlit run src/dashboard.py
```

---

## Testing Error Scenarios

```bash
# Test rate limit (send > RPM limit quickly)
for i in {1..25}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    http://localhost:8000/v1/chat/completions \
    -H "Authorization: Bearer eng-secret-key-abc123" \
    -H "X-Team-ID: engineering" \
    -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
done
# 429 appears after rate limit exceeded

# Test model allowlist
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer data-secret-key-xyz789" \
  -H "X-Team-ID: data-team" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}'
# 403 Forbidden — gpt-4o not in data-team's allowlist

# Test invalid key
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer wrong-key"
# 401 Unauthorized
```

---

## Deploy

### Docker Compose

```bash
docker-compose up
# Gateway: http://localhost:8000
# Dashboard: http://localhost:8501
```

Teams update their `base_url` to point at the gateway — zero other changes in their code.

---

## APIs / Secrets

| Service | Purpose | Cost | Required |
|---------|---------|------|----------|
| OpenAI API | Primary LLM provider | Normal rates | ✅ Yes |
| Anthropic API | Fallback provider | Normal rates | ⬜ Optional |

---

## Project Structure

```
11-llm-gateway/
├── src/
│   ├── main.py          # FastAPI gateway — auth, limits, routing, fallback
│   ├── rate_limiter.py  # Sliding window rate limit + budget tracker
│   └── dashboard.py     # Streamlit admin: team spend, provider health
├── config/
│   └── teams.yaml       # Team definitions (keys, budgets, allowlists)
├── gateway.db           # SQLite — request log + rate limit counters (auto-created)
├── requirements.txt
├── .env.example
└── README.md
```

---

*Part of the AI Engineering Portfolio — 15 production-grade AI projects*
