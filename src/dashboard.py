"""Streamlit gateway dashboard."""
import streamlit as st, sqlite3, pandas as pd
from pathlib import Path

DB = Path(__file__).parent.parent / "gateway.db"
st.set_page_config("LLM Gateway", "🚦", layout="wide")
st.title("🚦 LLM Gateway Dashboard")

if not DB.exists(): st.info("Start the gateway and send requests first."); st.stop()

conn = sqlite3.connect(DB)
reqs = pd.read_sql("SELECT * FROM requests ORDER BY id DESC", conn)
budget = pd.read_sql("SELECT * FROM budget_usage", conn)
conn.close()

if reqs.empty: st.info("No requests yet."); st.stop()

c1,c2,c3,c4 = st.columns(4)
c1.metric("Total Requests", len(reqs))
c2.metric("Total Cost", f"${reqs['cost_usd'].sum():.4f}")
c3.metric("Avg Latency", f"{reqs['latency_ms'].mean():.0f}ms")
c4.metric("Fallback Rate", f"{reqs['was_fallback'].mean():.1%}")

st.subheader("📊 Requests by Team")
team_stats = reqs.groupby("team").agg({"id":"count","cost_usd":"sum","latency_ms":"mean"}).round(4)
st.dataframe(team_stats, use_container_width=True)

st.subheader("💸 Budget Usage")
if not budget.empty: st.dataframe(budget, use_container_width=True)

st.subheader("📋 Recent Requests")
st.dataframe(reqs[["ts","team","model","provider","in_tok","out_tok","cost_usd","latency_ms","was_fallback"]].head(20), use_container_width=True)
