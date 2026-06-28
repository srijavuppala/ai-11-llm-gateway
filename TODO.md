# Project 11: LLM Gateway with Rate Limiting, Fallback Routing, and Observability

## What You're Building
A production API gateway in front of all LLM calls enforcing per-team rate limits and budgets, with multi-provider fallback routing and unified observability.

## Phases & Tasks

### Phase 1: Gateway Core (Day 1–3)
- [ ] FastAPI gateway with team authentication (API keys)
- [ ] Team config: allowed models, rate limits (RPM/TPM), monthly budget
- [ ] Unified request/response format across OpenAI + Anthropic + Cohere
- [ ] Streaming passthrough (forward chunks, log complete response)
- [ ] Request enrichment: inject team ID, request ID, timestamp into headers

### Phase 2: Rate Limiting & Budget Enforcement (Day 3–6)
- [ ] Redis-backed rate limiting: sliding window per team (RPM + TPM)
- [ ] Budget tracking: accumulate token costs, block when budget exceeded
- [ ] Rate limit headers in response: remaining/limit/reset
- [ ] Budget alerts: Slack notification at 80% and 100% budget

### Phase 3: Fallback Routing & Circuit Breakers (Day 6–9)
- [ ] Priority-ordered provider list per team config
- [ ] Retryable vs. non-retryable error detection
- [ ] Circuit breaker: open after N failures in M seconds, half-open after cooldown
- [ ] Automatic failover: on primary failure, route to next provider in list
- [ ] Log every failover and circuit breaker state change

### Phase 4: Observability (Day 9–11)
- [ ] Prometheus metrics: requests/sec, latency p50/p95/p99, error rate, cost per team
- [ ] Grafana dashboard: real-time traffic, team budget burn rate, provider health
- [ ] Request tracing: unique request ID propagated through all hops
- [ ] Cost attribution: which team is spending what on which models

### Phase 5: Admin API (Day 11–13)
- [ ] `GET /admin/teams` — team usage and budget status
- [ ] `POST /admin/teams` — create team with config
- [ ] `PUT /admin/teams/{id}/budget` — update budget without restart
- [ ] `GET /admin/providers` — provider health + circuit breaker state

### Phase 6: Polish (Day 13–14)
- [ ] Demo: simulate provider outage, show failover + circuit breaker in Grafana
- [ ] Benchmark: overhead measurement (target <10ms added latency)

## APIs Needed
| API | Purpose | Free Tier? |
|-----|---------|-----------|
| OpenAI API | Primary provider | $5 credit |
| Anthropic API | Fallback provider | $5 credit |
| Redis | Rate limit counters | Free OSS |
| Prometheus + Grafana | Observability | Free OSS |

## How to Test
```bash
# Start gateway
docker-compose up

# Send request as team-1
curl http://localhost:8000/v1/chat/completions \
  -H "X-Team-ID: team-1" \
  -H "Authorization: Bearer team-1-api-key" \
  -d '{"model": "gpt-4o", "messages": [...]}'

# Simulate rate limit
for i in {1..100}; do curl ...; done
# Should see 429 after limit

# Simulate outage (stop primary)
docker stop openai-mock
# Watch automatic failover to Anthropic
```

## How to Deploy
1. `docker-compose up -d` (gateway + Redis + Prometheus + Grafana)
2. Configure teams in `config/teams.yaml`
3. Point all internal services at `http://gateway:8000` instead of OpenAI

## Portfolio Talking Point
"I built an LLM gateway handling rate limits, per-team budgets, and automatic multi-provider failover with circuit breakers — the infrastructure every company needs before their second AI team spins up."
