"""LLM Gateway — rate limiting, budget enforcement, fallback routing."""
import os, yaml, time, json
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from openai import OpenAI, RateLimitError, APIError
from rate_limiter import check_rate_limit, check_budget, record_request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="LLM Gateway")

def load_config() -> dict:
    cfg_path = Path(__file__).parent.parent / "config/teams.yaml"
    return yaml.safe_load(cfg_path.read_text())["teams"]

TEAMS = load_config()
COST = {"gpt-4o": (5e-6,15e-6), "gpt-4o-mini": (0.15e-6,0.6e-6), "claude-haiku": (0.25e-6,1.25e-6)}

def get_team(request: Request) -> tuple[str, dict]:
    api_key = request.headers.get("Authorization","").replace("Bearer ","")
    team_id = request.headers.get("X-Team-ID","")
    for name, cfg in TEAMS.items():
        if cfg["api_key"] == api_key and (not team_id or team_id == name):
            return name, cfg
    raise HTTPException(401, "Invalid API key")

def call_openai(messages: list, model: str) -> tuple[str,int,int,float]:
    oa = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    t0 = time.perf_counter()
    r  = oa.chat.completions.create(model=model, messages=messages)
    ms = (time.perf_counter()-t0)*1000
    text = r.choices[0].message.content
    return text, r.usage.prompt_tokens, r.usage.completion_tokens, ms

@app.post("/v1/chat/completions")
async def gateway(request: Request):
    team_name, team_cfg = get_team(request)
    body  = await request.json()
    model = body.get("model","gpt-4o-mini")
    msgs  = body.get("messages",[])

    # Rate limit check
    ok, reason = check_rate_limit(team_name, team_cfg)
    if not ok: raise HTTPException(429, reason)
    
    # Budget check
    ok, budget_info = check_budget(team_name, team_cfg)
    if not ok: raise HTTPException(402, budget_info)

    # Model permission check
    allowed = team_cfg.get("allowed_models",[])
    if allowed and model not in allowed:
        raise HTTPException(403, f"Model {model} not allowed for team {team_name}. Allowed: {allowed}")

    # Try primary, fallback on error
    providers = team_cfg.get("providers",["openai"])
    was_fallback = False
    last_error = None
    
    for i, provider in enumerate(providers):
        try:
            if provider == "openai":
                text, in_tok, out_tok, ms = call_openai(msgs, model)
            else:
                raise NotImplementedError(f"Provider {provider} not configured")
            
            costs = COST.get(model, (0.15e-6, 0.6e-6))
            cost  = in_tok*costs[0] + out_tok*costs[1]
            record_request(team_name, in_tok, out_tok, cost, model, ms, provider, was_fallback)
            
            return JSONResponse({
                "choices": [{"message":{"role":"assistant","content":text},"finish_reason":"stop"}],
                "model": model, "usage": {"prompt_tokens":in_tok,"completion_tokens":out_tok},
                "x_team": team_name, "x_provider": provider, "x_fallback": was_fallback,
            }, headers={"x-team":team_name,"x-provider":provider})
        except (RateLimitError, APIError) as e:
            last_error = str(e); was_fallback = True; continue
    
    raise HTTPException(503, f"All providers failed. Last error: {last_error}")

@app.get("/admin/teams")
async def admin_teams(request: Request):
    from rate_limiter import DB
    import sqlite3
    c = sqlite3.connect(DB)
    rows = c.execute("SELECT team, SUM(cost_usd), COUNT(*), AVG(latency_ms) FROM requests GROUP BY team").fetchall()
    c.close()
    return [{"team":r[0],"total_cost":r[1],"requests":r[2],"avg_latency_ms":r[3]} for r in rows]

@app.get("/health")
def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=8000)
