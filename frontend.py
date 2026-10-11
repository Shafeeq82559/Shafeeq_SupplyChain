"""Streamlit front end for the Supply Chain Disruption Assistant.

Run (with the API running):  streamlit run frontend.py
"""
import ast
import json
import os
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
TYPES = ["Port Congestion", "Geopolitical", "Labor Strike", "Natural Disaster", "Cyber Attack", "Factory Incident"]
INDUSTRIES = ["Electronics", "Automotive", "Consumer Goods", "Pharmaceuticals", "Aerospace"]
REGIONS = ["Asia-Pacific", "Europe", "North America", "South America", "Africa/Middle East"]
SIZES = ["Small", "Medium", "Large"]
RESPONSES = ["Alternative Supplier", "Production Reroute", "Inventory Buffer", "Customer Delay", "Combined Strategy"]

# Palette: nautical chart paper, hull ink, sea-lane teal, hazard amber, corten rust
PAPER, INK, TEAL, AMBER, RUST, FOG, MUTED = "#EEF1EE", "#18262F", "#0E6E6B", "#E9A400", "#B23A26", "#CBD4D2", "#5A6B72"
ACCENT = TEAL
PRIORITY_COLORS = {"P1": RUST, "P2": "#D9711C", "P3": "#B98900", "P4": "#2E7D5B"}
RISK_SCALE = [[0, TEAL], [0.5, AMBER], [1, RUST]]
SEA_SCALE = [[0, "#DCE7E4"], [1, TEAL]]
HEAT_SCALE = [[0, "#3E8C88"], [0.5, "#F4ECD2"], [1, "#C0563F"]]
EXAMPLES = {
    "Typhoon hits Taiwan chip plant": "A typhoon flooded our Tier-1 semiconductor supplier's plant in Taiwan. Production is severely halted for weeks and we have no backup supplier.",
    "Ransomware at German auto supplier": "Ransomware attack has locked the ERP systems of our Tier-2 auto parts supplier in Germany; shipments stopped for 5 days.",
    "Port strike delays pharma inputs": "Dock workers union strike at the port is delaying containers of pharma active ingredients from India. Moderate delays so far, we have a backup supplier.",
    "Sanctions block titanium": "New export sanctions blocked titanium deliveries from our aerospace components supplier in the Middle East.",
}

pio.templates["lane"] = go.layout.Template(layout=dict(
    font=dict(family="Archivo, sans-serif", color=INK, size=13),
    colorway=[TEAL, AMBER, "#3C5A73", RUST, "#7FA38F", "#9AA5AB"],
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
    xaxis=dict(gridcolor="#DCE2E0", zerolinecolor=FOG, linecolor=FOG, tickfont=dict(color=MUTED)),
    yaxis=dict(gridcolor="#DCE2E0", zerolinecolor=FOG, linecolor=FOG, tickfont=dict(color=MUTED)),
    hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(color="white", family="Archivo, sans-serif")),
    legend=dict(font=dict(color=MUTED)),
    coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=10, tickfont=dict(color=MUTED))),
))
pio.templates.default = "plotly_white+lane"

st.set_page_config(page_title="Supply Chain Disruption Assistant", page_icon="🚢", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,300..800&display=swap');
:root {
  --paper:#EEF1EE; --ink:#18262F; --teal:#0E6E6B; --amber:#E9A400; --rust:#B23A26;
  --fog:#CBD4D2; --muted:#5A6B72; --surface:#F8FAF8;
}
html, body, .stApp {font-family:'Archivo', sans-serif;}
.stApp {background:var(--paper);}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.2rem; max-width:1320px;}
.stApp p, .stApp li {line-height:1.55;}
h1, h2, h3, h4 {font-stretch:80%; letter-spacing:-0.01em; color:var(--ink);}

/* ---------- hero: the shipping lane ---------- */
.lane-hero {position:relative; overflow:hidden; background:var(--ink); color:#E8EEEC;
  border-radius:10px; padding:30px 34px 26px; margin-bottom:6px;}
.lane-hero .graticule {position:absolute; inset:0; width:100%; height:100%; opacity:.22; pointer-events:none;}
.lane-hero h1 {color:#F4F7F5; font-size:clamp(2rem, 4.2vw, 3.2rem); font-weight:780; font-stretch:68%;
  line-height:.98; margin:0 0 10px; padding:0; letter-spacing:-0.005em; position:relative;}
.lane-hero .lede {max-width:62ch; color:#B9C6C3; font-size:1rem; margin:0 0 28px; position:relative;}
.route {position:relative; margin:0 6px;}
.route .rail {position:absolute; top:7px; left:7px; right:7px; height:2px; background:repeating-linear-gradient(90deg, #4A5B64 0 6px, transparent 6px 12px);}
.route .rail-live {position:absolute; top:7px; left:7px; height:2px; background:var(--teal); width:0;
  animation:rail-grow 1.6s cubic-bezier(.3,.7,.2,1) .2s forwards;}
.route .rail-live::after {content:""; position:absolute; inset:0;
  background:repeating-linear-gradient(90deg, rgba(255,255,255,.55) 0 3px, transparent 3px 22px);
  background-size:22px 2px; animation:lane-flow 1.4s linear infinite; opacity:.55;}
.route .cargo {position:absolute; top:1px; left:7px; width:20px; height:12px; margin-left:-10px; border-radius:2px;
  background:var(--amber); box-shadow:0 0 0 3px rgba(233,164,0,.18);
  animation:cargo-sail 1.6s cubic-bezier(.3,.7,.2,1) .2s forwards;}
.route .cargo::before {content:""; position:absolute; inset:2px 4px; border-left:1.5px solid rgba(24,38,47,.45);
  border-right:1.5px solid rgba(24,38,47,.45);}
.stops {display:flex; justify-content:space-between; position:relative;}
.stop {display:flex; flex-direction:column; align-items:flex-start; gap:8px; min-width:0;}
.stop:last-child {align-items:flex-end; text-align:right;}
.stop:not(:first-child):not(:last-child) {align-items:center; text-align:center;}
.stop .pin {width:16px; height:16px; border-radius:50%; background:var(--ink); border:2px solid #4A5B64; position:relative; z-index:1;}
.stop.ok .pin {border-color:var(--teal); background:var(--teal); box-shadow:inset 0 0 0 3px var(--ink);}
.stop.warn .pin {border-color:var(--amber); animation:beacon 2.4s ease-out infinite;}
.stop.down .pin {border-color:var(--rust);}
.stop .name {font-size:.92rem; font-weight:600; color:#F4F7F5; font-stretch:85%;}
.stop .state {font-size:.8rem; color:#9AAAA7; margin-top:-6px;}
.stop.warn .state {color:var(--amber);} .stop.down .state {color:#E7897A;}
@keyframes rail-grow {to {width:calc(var(--reach) - 14px);}}
@keyframes cargo-sail {to {left:calc(var(--reach) - 7px);}}
@keyframes lane-flow {to {background-position:22px 0;}}
@keyframes beacon {0% {box-shadow:0 0 0 0 rgba(233,164,0,.55);} 70%,100% {box-shadow:0 0 0 10px rgba(233,164,0,0);}}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] {gap:26px; border-bottom:1px solid var(--fog);}
.stTabs [data-baseweb="tab"] {padding:14px 0 12px; background:transparent; height:auto;}
.stTabs [data-baseweb="tab"] p {font-size:1.02rem; font-weight:560; color:var(--muted); font-stretch:88%;}
.stTabs [data-baseweb="tab"][aria-selected="true"] p {color:var(--ink);}
.stTabs [data-baseweb="tab"]:hover p {color:var(--teal);}
.stTabs [data-baseweb="tab-highlight"] {background:var(--teal); height:3px; border-radius:2px 2px 0 0;}
.stTabs [data-baseweb="tab-border"] {display:none;}
.stTabs .stTabs [data-baseweb="tab-list"] {gap:20px;}
.stTabs .stTabs [data-baseweb="tab"] p {font-size:.92rem;}

/* ---------- widgets ---------- */
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button {font-weight:640; padding:.55rem 1.3rem;
  letter-spacing:.01em; transition:transform .12s ease, box-shadow .12s ease;}
.stButton button[kind="primary"]:hover {box-shadow:0 4px 14px -6px rgba(14,110,107,.7); transform:translateY(-1px);}
.stButton button:focus-visible, .stTabs [data-baseweb="tab"]:focus-visible {outline:2px solid var(--amber); outline-offset:2px;}
[data-testid="stExpander"] details {background:var(--surface); border-color:var(--fog);}
[data-testid="stTextArea"] textarea {font-size:1.02rem; line-height:1.5;}
[data-testid="stMetric"] {border-left:1px solid var(--fog); padding:4px 0 4px 14px;}
[data-testid="stMetricValue"] {font-size:1.5rem; font-weight:700; font-stretch:75%; font-variant-numeric:tabular-nums;}
[data-testid="stMetricLabel"] p {color:var(--muted);}

/* ---------- section intros ---------- */
.intro {margin:18px 0 14px;}
.intro h2 {font-size:1.7rem; font-weight:740; font-stretch:72%; margin:0 0 4px; padding:0;}
.intro p {color:var(--muted); max-width:72ch; margin:0;}
.subhead {font-size:1.15rem; font-weight:700; font-stretch:78%; margin:26px 0 8px; color:var(--ink);}
.muted {color:var(--muted); font-size:.88rem;}

/* ---------- hazard placard (priority) ---------- */
.placard {display:inline-flex; align-items:stretch; border:1.5px solid var(--c); border-radius:4px; overflow:hidden;
  font-size:.9rem; line-height:1; vertical-align:middle; background:#fff;}
.placard b {background:var(--c); color:#fff; padding:7px 9px; font-weight:780; font-stretch:75%;}
.placard span {padding:7px 10px; color:var(--c); font-weight:640;}
.placard em {font-style:normal; padding:7px 10px 7px 0; color:var(--muted); font-variant-numeric:tabular-nums;}

/* ---------- analysis header ---------- */
.verdict {display:flex; flex-wrap:wrap; align-items:center; gap:14px; margin:22px 0 12px;}
.verdict h3 {margin:0; padding:0; font-size:1.55rem; font-weight:740; font-stretch:72%;}
.dispatch {border-left:3px solid var(--teal); padding:4px 0 4px 18px; margin:6px 0 20px; font-size:1.06rem;
  line-height:1.6; max-width:78ch; color:var(--ink);}
.reveal {animation:rise .5s ease-out both; animation-delay:calc(var(--i, 0) * 70ms);}
@keyframes rise {from {opacity:0; transform:translateY(8px);}}

/* ---------- readout strip ---------- */
.readouts {display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); border-top:2px solid var(--ink);
  border-bottom:1px solid var(--fog); margin:4px 0 14px;}
.ro {padding:12px 18px 14px; border-left:1px solid var(--fog);}
.ro:first-child {border-left:none; padding-left:2px;}
.ro-label {font-size:.84rem; color:var(--muted);}
.ro-value {font-size:2rem; font-weight:720; font-stretch:70%; font-variant-numeric:tabular-nums; line-height:1.15; margin:2px 0 6px;}
.ro-value.rust {color:var(--rust);} .ro-value.teal {color:var(--teal);}
.ro-range {position:relative; height:6px; background:#DCE2E0; border-radius:3px; margin:2px 0 6px;}
.ro-band {position:absolute; top:0; bottom:0; background:rgba(14,110,107,.35); border-radius:3px;
  transform-origin:left; animation:band .8s cubic-bezier(.3,.7,.2,1) both; animation-delay:calc(var(--i,0) * 70ms + .15s);}
.ro-mark {position:absolute; top:-3px; width:3px; height:12px; margin-left:-1.5px; background:var(--ink); border-radius:1px;}
.ro-note {font-size:.8rem; color:var(--muted); font-variant-numeric:tabular-nums;}
@keyframes band {from {transform:scaleX(0);}}

/* ---------- route lists: agent trace + ranking ---------- */
.trace {list-style:none; margin:8px 0 0 !important; padding:0 !important; position:relative;}
.trace::before {content:""; position:absolute; left:9px; top:10px; bottom:14px; width:2px; background:var(--fog);}
.trace li {position:relative; padding:0 0 18px 34px; margin:0 !important;}
.trace li::before {content:""; position:absolute; left:2px; top:3px; width:16px; height:16px; border-radius:50%;
  background:var(--paper); border:2.5px solid var(--teal);}
.trace li.blocked::before {border-color:var(--rust); background:var(--rust);}
.trace .agent {font-weight:700; font-stretch:82%;}
.trace .ms {color:var(--muted); font-size:.82rem; font-variant-numeric:tabular-nums; margin-left:6px;}
.trace p {margin:2px 0 0; color:#33444D; max-width:90ch;}
.ranked {border-top:2px solid var(--ink); margin:10px 0 8px;}
.ranked .row {display:grid; grid-template-columns:44px 156px 1fr minmax(110px, 180px); gap:16px; align-items:center;
  padding:12px 4px; border-bottom:1px solid var(--fog);}
.ranked .rank {font-size:1.5rem; font-weight:760; font-stretch:68%; color:var(--muted); font-variant-numeric:tabular-nums;}
.ranked .what b {display:block; font-weight:680;}
.ranked .what span {color:var(--muted); font-size:.88rem;}
.ranked .placard {justify-self:start;}
.ranked .meter {height:6px; background:#DCE2E0; border-radius:3px; overflow:hidden;}
.ranked .meter i {display:block; height:100%; background:var(--c); transform-origin:left;
  animation:band .9s cubic-bezier(.3,.7,.2,1) both; animation-delay:calc(var(--i,0) * 70ms + .2s);}

.ranked.strat .row {grid-template-columns:34px minmax(230px,1.5fr) minmax(110px,1fr) repeat(3, minmax(86px,.55fr)); gap:14px;}
.ranked.strat .row.top {background:rgba(14,110,107,.08); box-shadow:inset 3px 0 0 var(--teal);}
.strat .stat b {display:block; font-weight:680; font-variant-numeric:tabular-nums;}
.strat .stat span, .strat .score span {color:var(--muted); font-size:.8rem;}
.strat .score .meter {margin-bottom:4px;}
.ranked .what b .tag {display:inline-block; margin-left:10px; padding:2px 7px; border-radius:3px; background:var(--teal); color:#fff;
  font-size:.68rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; vertical-align:2px; white-space:nowrap;}
.chips {display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px;}
.chip {border:1px solid var(--fog); background:var(--surface); border-radius:999px; padding:3px 11px; font-size:.84rem; color:var(--ink);}
.chip i {font-style:normal; color:var(--muted); margin-right:5px;}
.kpis {display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 4px;}
.kpis span {border-left:3px solid var(--teal); background:var(--surface); padding:6px 12px; font-size:.9rem;}

/* ---------- recovery milestones lane ---------- */
.track {position:relative; height:200px; margin:8px 22px 10px;}
.track .line {position:absolute; left:0; right:0; top:99px; height:2px; background:var(--fog);}
.track .line::after {content:""; position:absolute; inset:0; background:var(--teal); transform-origin:left;
  animation:band 1.2s cubic-bezier(.3,.7,.2,1) both;}
.mstone {position:absolute; top:92px; transform:translateX(-50%); width:16px;}
.mstone .dot {display:block; width:16px; height:16px; border-radius:50%; background:var(--paper); border:2.5px solid var(--teal);}
.mstone.last .dot {background:var(--teal);}
.mstone .lbl {position:absolute; left:50%; transform:translateX(-50%); width:170px; text-align:center; font-size:.82rem; line-height:1.3;}
.mstone .lbl b {display:block; font-stretch:78%; font-size:.95rem;}
.mstone.up .lbl {bottom:26px;} .mstone.down .lbl {top:26px;}
.mstone.first .lbl {left:-4px; transform:none; text-align:left;}
.mstone.last .lbl {left:auto; right:-4px; transform:none; text-align:right;}

/* ---------- loader ---------- */
.loader {padding:18px 0 8px; max-width:560px;}
.loader .lane {position:relative; height:12px; margin-bottom:12px;}
.loader .lane::before {content:""; position:absolute; left:0; right:0; top:5px; height:2px;
  background:repeating-linear-gradient(90deg, var(--fog) 0 8px, transparent 8px 14px);}
.loader .box {position:absolute; top:0; width:20px; height:12px; border-radius:2px; background:var(--amber);
  animation:ferry 2.6s ease-in-out infinite alternate;}
.loader .steps {position:relative; height:1.5em; color:var(--ink); font-weight:600;}
.loader .steps span {position:absolute; left:0; opacity:0;
  animation:step var(--total) linear infinite; animation-delay:calc(var(--i) * var(--each));}
.loader.single .steps span {opacity:1; animation:none;}
@keyframes ferry {from {left:0;} to {left:calc(100% - 20px);}}
@keyframes step {0% {opacity:0; transform:translateY(6px);} 3% {opacity:1; transform:none;}
  14% {opacity:1; transform:none;} 16.6% {opacity:0; transform:translateY(-4px);} 100% {opacity:0;}}

@media (max-width: 720px) {
  .lane-hero {padding:22px 18px 20px;}
  .stop .state {display:none;}
  .stop .name {font-size:.78rem;}
  .ranked .row, .ranked.strat .row {grid-template-columns:32px 1fr 1fr 1fr; gap:8px 12px;}
  .ranked.strat .what, .ranked.strat .score {grid-column:2 / -1;}
  .ranked .what, .ranked .placard {grid-column:2;}
  .ranked .meter {grid-column:2;}
  .track {height:auto; margin:10px 0;}
  .track .line {display:none;}
  .mstone {position:static; transform:none; width:auto; display:flex; gap:10px; margin-bottom:10px;}
  .mstone .dot {flex:none;}
  .mstone .lbl, .mstone.first .lbl, .mstone.last .lbl {position:static; transform:none; width:auto; text-align:left;}
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {animation-duration:.01ms !important; animation-iteration-count:1 !important; transition:none !important;}
  .loader .steps span:first-child {opacity:1;}
}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers
def api(method: str, path: str, payload: dict | None = None, timeout: int = 180):
    try:
        r = requests.request(method, f"{API_URL}{path}", json=payload, timeout=timeout)
    except requests.RequestException:
        st.error(f"Cannot reach the API at {API_URL}. Start it with: `uvicorn src.main:app --reload`")
        return None
    if r.status_code == 422:
        detail = r.json().get("detail", r.json())
        violations = detail.get("violations") if isinstance(detail, dict) else None
        st.warning("Input rejected by guardrails: " + ("; ".join(
            v if isinstance(v, str) else f"{v.get('field')}: {v.get('message')}" for v in violations) if violations else str(detail)))
        return None
    if not r.ok:
        st.error(f"API error {r.status_code}: {r.text[:300]}")
        return None
    return r.json()


def html(markup: str):
    st.markdown(markup, unsafe_allow_html=True)


def badge(level: str, label: str, score: float | None = None) -> str:
    s = f"<em>{score:.0f}</em>" if score is not None else ""
    return f'<span class="placard" style="--c:{PRIORITY_COLORS.get(level, MUTED)}"><b>{level}</b><span>{label}</span>{s}</span>'


def md(text) -> str:
    """Escape dollar signs so Streamlit markdown doesn't render amounts as LaTeX math."""
    return str(text).replace("$", r"\$")


def fact_sheet_md(text: str) -> str:
    """Readable layout for the LLM fact sheet: ALL-CAPS section labels become bold headings, example cases stay bullets."""
    out = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([A-Z][A-Z0-9 ]+?)(?= \(| - |:)", line)
        if line.startswith("- "):
            out.append(md(line) if out and out[-1].startswith("- ") else "\n" + md(line))
        elif m:
            rest = line[m.end():].lstrip(" :-")
            note = ""
            if rest.startswith("(") and ") - " in rest:
                note, rest = rest[:rest.index(") - ") + 1], rest[rest.index(") - ") + 4:]
            elif rest.startswith("(") and rest.endswith("):"):
                note, rest = rest[:-1], ""
            out.append(f"\n**{m.group(1).capitalize()}**" + (f" *{md(note)}*" if note else "") + f"  \n{md(rest)}")
        else:
            out.append(f"\n{md(line)}")
    return "\n".join(out)


def html_text(text) -> str:
    """For text placed inside raw HTML blocks (markdown escapes don't apply there)."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace("$", "&#36;")


def tidy(text) -> str:
    """Rewrite Python dict literals that leak into backend summaries, e.g. {'industry': 'Automotive'} -> industry Automotive."""
    def fix(m):
        try:
            d = ast.literal_eval(m.group(0))
        except (ValueError, SyntaxError):
            return m.group(0)
        return "(" + ", ".join(f"{FILTER_LABELS.get(k, k.replace('_', ' '))} {v}" for k, v in d.items()) + ")"
    return re.sub(r"\{[^{}]*\}", fix, str(text))


def money(v: float) -> str:
    return f"${v / 1e6:,.2f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


def intro(title: str, text: str):
    html(f'<div class="intro"><h2>{title}</h2><p>{text}</p></div>')


def subhead(text: str):
    html(f'<div class="subhead">{text}</div>')


def loader(steps: list[str]) -> str:
    each = 2.5
    spans = "".join(f'<span style="--i:{i}">{s}</span>' for i, s in enumerate(steps))
    cls = "loader single" if len(steps) == 1 else "loader"
    return (f'<div class="{cls}" style="--each:{each}s; --total:{each * len(steps)}s" role="status">'
            f'<div class="lane"><span class="box"></span></div><div class="steps">{spans}</div></div>')


def readouts(items: list[dict]):
    """A manifest-style strip of key numbers. Items with lo/hi get a likely-range bar (p10–p90)."""
    cells = []
    for i, it in enumerate(items):
        bar = ""
        if it.get("hi") is not None:
            top = it.get("max") or max(it["hi"] * 1.15, 1e-9)
            lo, hi, mid = (100 * min(it[k] / top, 1) for k in ("lo", "hi", "mid"))
            bar = (f'<div class="ro-range"><span class="ro-band" style="left:{lo:.1f}%; width:{max(hi - lo, 1):.1f}%"></span>'
                   f'<span class="ro-mark" style="left:{mid:.1f}%"></span></div>')
        note = f'<div class="ro-note">{html_text(it["note"])}</div>' if it.get("note") else ""
        cells.append(f'<div class="ro reveal" style="--i:{i}"><div class="ro-label">{it["label"]}</div>'
                     f'<div class="ro-value {it.get("tone", "")}">{html_text(it["value"])}</div>{bar}{note}</div>')
    html(f'<div class="readouts">{"".join(cells)}</div>')


def chart(fig, height: int | None = None):
    fig.update_layout(margin=dict(l=8, r=8, t=44 if fig.layout.title.text else 12, b=8), legend_title="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      **({"height": height} if height else {}))
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def cases_table(cases: list[dict]):
    if not cases:
        st.info("No matching disruptions. Widen the filters or rephrase the search.")
        return
    df = pd.DataFrame(cases)
    if "revenue_loss_usd" in df:
        df["revenue_loss_usd"] = df["revenue_loss_usd"] / 1e6
    cols =[c for c in ["disruption_id", "disruption_type", "industry", "supplier_region", "supplier_tier",
                        "disruption_severity", "production_impact_pct", "revenue_loss_usd", "response_type",
                        "full_recovery_days", "permanent_supplier_change", "hybrid_score", "semantic_score",
                        "keyword_score"] if c in df]
    st.dataframe(df[cols], hide_index=True, width="stretch", column_config={
        "disruption_id": "case", "disruption_type": "type", "supplier_region": "region", "supplier_tier": "tier",
        "disruption_severity": "severity", "response_type": "response", "full_recovery_days": "recovery days",
        "permanent_supplier_change": "supplier changed",
        "revenue_loss_usd": st.column_config.NumberColumn("revenue loss", format="$%.2fM"),
        "production_impact_pct": st.column_config.NumberColumn("impact %", format="%.1f"),
        "hybrid_score": st.column_config.ProgressColumn("match", min_value=0, max_value=1, format="%.2f"),
    })


FILTER_LABELS = {"disruption_type": "type", "industry": "industry", "supplier_region": "region", "supplier_tier": "tier",
                 "response_type": "response", "has_backup_supplier": "backup"}


def filter_chips(filters: dict) -> str:
    """The applied search filters as small labelled chips instead of a raw dict."""
    chips = []
    for k, v in (filters or {}).items():
        if k in ("min_severity", "max_severity"):
            continue
        v = ", ".join(map(str, v)) if isinstance(v, list) else ("yes" if v is True else "no" if v is False else v)
        chips.append(f'<span class="chip"><i>{FILTER_LABELS.get(k, k.replace("_", " "))}</i>{html_text(v)}</span>')
    lo, hi = (filters or {}).get("min_severity"), (filters or {}).get("max_severity")
    if lo is not None or hi is not None:
        chips.append(f'<span class="chip"><i>severity</i>{lo if lo is not None else 1}–{hi if hi is not None else 5}</span>')
    return f'<div class="chips">{"".join(chips)}</div>' if chips else ""


def strategy_rows(ranking: list[dict], recommended: str | None):
    """Ranked strategies as a manifest: score meter plus the three numbers that decide between them."""
    top = max((r["strategy_score"] for r in ranking), default=1) or 1
    rows = []
    for i, r in enumerate(ranking):
        best = r["response_type"] == (recommended or ranking[0]["response_type"])
        tag = '<span class="tag">Recommended</span>' if best else ""
        n = r.get("evidence_cases") or 0
        sub = f"used in {n} of {r['evidence_total']} similar cases" if n else "no similar case used it; model estimate only"
        if r.get("feasible_now") is False:
            sub += f'</span><span>{html_text(r["feasibility_note"])}'
        rows.append(
            f'<div class="row {"top" if best else ""} reveal" style="--i:{i}"><span class="rank">{r["rank"]}</span>'
            f'<div class="what"><b>{html_text(r["response_type"])}{tag}</b><span>{sub}</span></div>'
            f'<div class="score"><div class="meter" style="--c:{TEAL if best else "#9AA5AB"}"><i style="width:{100 * r["strategy_score"] / top:.0f}%"></i></div>'
            f'<span>score {r["strategy_score"]:.0f}</span></div>'
            f'<div class="stat"><b>{r["expected_full_recovery_days"]:.0f} days</b><span>full recovery</span></div>'
            f'<div class="stat"><b>{money(r["expected_revenue_loss_usd"])}</b><span>revenue loss</span></div>'
            f'<div class="stat"><b>{100 * r["supplier_change_risk"]:.0f}%</b><span>supplier change</span></div></div>')
    html(f'<div class="ranked strat">{"".join(rows)}</div>')


def shap_bar(contribs: list[dict], unit: str, title: str):
    df = pd.DataFrame(contribs)
    df["name"] = df["label"] + " = " + df["value"].astype(str)
    df = df.iloc[::-1]
    fig = go.Figure(go.Bar(x=df["contribution"], y=df["name"], orientation="h",
                           marker_color=[RUST if v > 0 else TEAL for v in df["contribution"]]))
    fig.update_layout(title=title, xaxis_title=unit, bargap=0.35)
    chart(fig, 320)


def milestone_track(milestones: list[dict]):
    if not milestones:
        return
    last = max(m["day"] for m in milestones) or 1
    stops, ms = [], sorted(milestones, key=lambda m: m["day"])
    for i, m in enumerate(ms):
        pos = 100 * m["day"] / last
        edge = " first" if i == 0 else " last" if i == len(ms) - 1 else ""
        stops.append(f'<div class="mstone {"up" if i % 2 == 0 else "down"}{edge} reveal" style="left:{pos:.1f}%; --i:{i + 3}">'
                     f'<span class="dot"></span><span class="lbl"><b>Day {m["day"]:.0f}</b>{html_text(m["milestone"])}</span></div>')
    html(f'<div class="track"><div class="line"></div>{"".join(stops)}</div>')


def profile_form(key: str, with_response: bool = False) -> dict:
    c1, c2, c3, c4 = st.columns(4)
    p = {"disruption_type": c1.selectbox("Disruption type", TYPES, index=3, key=f"{key}t"),
         "industry": c2.selectbox("Industry", INDUSTRIES, key=f"{key}i"),
         "supplier_region": c3.selectbox("Supplier region", REGIONS, key=f"{key}r"),
         "supplier_tier": c4.selectbox("Supplier tier", [1, 2, 3, 4], key=f"{key}tier")}
    c1, c2, c3, c4 = st.columns(4)
    p["supplier_size"] = c1.selectbox("Supplier size", SIZES, index=1, key=f"{key}s")
    p["disruption_severity"] = c2.slider("Severity", 1, 5, 4, key=f"{key}sev")
    if with_response:
        p["response_type"] = c3.selectbox("Response strategy", RESPONSES, key=f"{key}resp")
    c4.write("")
    p["has_backup_supplier"] = c4.toggle("Backup supplier available", key=f"{key}b")
    return p


OVERRIDE_LABELS = {"disruption_type": "Type", "industry": "Industry", "supplier_region": "Region", "supplier_tier": "Tier",
                   "supplier_size": "Size", "has_backup_supplier": "Backup supplier", "disruption_severity": "Severity"}


def clear_overrides():
    """Reset the 'Add details' boxes (button callback, runs before the widgets are drawn again)."""
    for k in ("ovt", "ovi", "ovr", "ovtier", "ovs", "ovsev"):
        st.session_state[k] = None
    st.session_state["ovb"] = "Unknown"
    st.session_state["ovobs"] = 0.0


# ---------------------------------------------------------------- header: the system as a shipping lane
health = None
try:
    health = requests.get(f"{API_URL}/health", timeout=5).json()
except requests.RequestException:
    pass

if health:
    llm = health["llm"]
    stations = [("API", "ok", "connected"),
                ("Language model", "ok" if llm["enabled"] else "warn", llm["model"] if llm["enabled"] else "offline, using fallbacks"),
                ("Case index", "ok" if health["index_ready"] else "down", "100k disruptions" if health["index_ready"] else "not loaded"),
                ("Impact models", "ok" if health["models_ready"] else "down", "ready" if health["models_ready"] else "not loaded")]
else:
    stations = [("API", "down", "not reachable"), ("Language model", "idle", "waiting"),
                ("Case index", "idle", "waiting"), ("Impact models", "idle", "waiting")]
# the container sails as far as the first station that is down
reach_idx = next((i for i, (_, s, _) in enumerate(stations) if s in ("down", "idle")), len(stations))
reach_idx = max(reach_idx - 1, 0) if reach_idx < len(stations) else len(stations) - 1
reach = f"{100 * reach_idx / (len(stations) - 1):.0f}%"
stop_html = "".join(f'<div class="stop {s}"><span class="pin"></span><span class="name">{n}</span>'
                    f'<span class="state">{html_text(d)}</span></div>' for n, s, d in stations)
graticule = "".join(f'<path d="M{x} -10 Q{x + 60} 120 {x - 20} 240" />' for x in range(40, 1300, 120)) + \
            "".join(f'<path d="M-10 {y} Q600 {y - 26} 1210 {y}" />' for y in (40, 95, 150, 205))
html(f"""
<div class="lane-hero">
  <svg class="graticule" viewBox="0 0 1200 230" preserveAspectRatio="none" aria-hidden="true">
    <g fill="none" stroke="#6F8B88" stroke-width="1" vector-effect="non-scaling-stroke">{graticule}</g></svg>
  <h1>Supply Chain Disruption Assistant</h1>
  <p class="lede">Describe what broke. Six agents check it against 100,000 past disruptions, estimate the damage
  and recovery time, and recommend a response you can defend.</p>
  <div class="route" style="--reach:{reach}" aria-label="System status">
    <div class="rail"></div><div class="rail-live"></div><div class="cargo"></div>
    <div class="stops">{stop_html}</div>
  </div>
</div>""")
if not health:
    st.error("The API isn't responding. If you just started it, give it about 30 seconds to load the index and models.")
    if st.button("Retry connection"):
        st.rerun()

LLM_LABELS = {"nvidia": "NVIDIA (free, slower)", "aicredits": "AICredits gpt-5-nano (faster)",
              "gemini": "Gemini", "anthropic": "Claude (Anthropic)", "ollama": "Ollama (local)", "off": "Off (instant templates)"}
if health:
    try:
        provs = requests.get(f"{API_URL}/llm/providers", timeout=5).json()["providers"]
    except (requests.RequestException, KeyError, ValueError):
        provs = []
    if provs:
        options = [p["provider"] for p in provs if p["available"] and p["provider"] != "ollama"] + ["off"]
        current = next((p["provider"] for p in provs if p["active"]), "off")
        choice = st.segmented_control("Language model for plans and judging", options, default=current,
                                      format_func=LLM_LABELS.get, key=f"llm_pick_{current}")
        if choice and choice != current:
            if api("POST", "/llm/provider", {"provider": choice}):
                st.rerun()

tabs = st.tabs(["Analyze", "Similar cases", "Prioritize", "Predict & explain", "Risk & resilience", "Insights", "Evaluation"])

# ---------------------------------------------------------------- 1. Analyze
with tabs[0]:
    intro("Analyze a disruption", "Describe it in plain language. Agents classify it, find similar past cases, "
          "assess the impact, plan a response, map the recovery and check the result before you see it.")
    shared_q = st.query_params.get("q")  # shareable link: ?q=<description> pre-fills and runs the analysis
    ex = st.pills("Try an example", list(EXAMPLES), key="ex")
    default_q = shared_q or EXAMPLES.get(ex, "")
    query = st.text_area("What happened?", value=default_q, height=110,
                         placeholder="e.g. Flooding closed our Tier-1 resin supplier in Thailand; no backup, output down by half.")
    with st.expander("Add details you already know (they override what the agents infer)"):
        c1, c2, c3, c4 = st.columns(4)
        ov = {"disruption_type": c1.selectbox("Type", [None] + TYPES, key="ovt"),
              "industry": c2.selectbox("Industry", [None] + INDUSTRIES, key="ovi"),
              "supplier_region": c3.selectbox("Region", [None] + REGIONS, key="ovr"),
              "supplier_tier": c4.selectbox("Tier", [None, 1, 2, 3, 4], key="ovtier")}
        c1, c2, c3, c4 = st.columns(4)
        ov["supplier_size"] = c1.selectbox("Size", [None] + SIZES, key="ovs")
        ov["has_backup_supplier"] = {"Unknown": None, "Yes": True, "No": False}[c2.radio("Backup supplier", ["Unknown", "Yes", "No"], horizontal=True, key="ovb")]
        ov["disruption_severity"] = c3.selectbox("Severity", [None, 1, 2, 3, 4, 5], key="ovsev")
        obs_impact = c4.number_input("Observed impact % (optional)", 0.0, 100.0, 0.0, key="ovobs")
        st.button("Clear all details", on_click=clear_overrides)
    auto_run = bool(shared_q) and not st.session_state.get("auto_ran")
    if st.button("Analyze disruption", type="primary", disabled=len(query.strip()) < 3) or auto_run:
        st.session_state["auto_ran"] = True
        payload = {"query": query, "profile": {k: v for k, v in ov.items() if v is not None}}
        if obs_impact > 0:
            payload["production_impact_pct"] = obs_impact
        st.session_state["analysis_overrides"] = dict(payload["profile"])
        wait = st.empty()
        wait.markdown(loader(["Classifying the disruption", "Searching 100,000 past cases", "Estimating the impact",
                              "Planning the response", "Mapping the recovery", "Checking the answer"]), unsafe_allow_html=True)
        st.session_state["analysis"] = api("POST", "/analyze", payload, timeout=300)
        st.session_state["fb_sent"] = False
        wait.empty()

    a = st.session_state.get("analysis")
    if a:
        imp, pr = a["impact_assessment"]["predictions"], a["impact_assessment"]["priority"]
        plan, rec, j = a["response"]["plan"], a["recovery"], a["judgement"]
        p_ = a["profile"]
        html(f'<div class="verdict reveal">{badge(pr["priority_level"], pr["priority_label"], pr["priority_score"])}'
             f'<h3>{p_["disruption_type"]} in {p_["industry"].lower()}, {p_["supplier_region"]}</h3></div>'
             f'<div class="dispatch reveal" style="--i:1">{html_text(a["executive_summary"])}</div>')
        pi, rl, fr = imp["production_impact_pct"], imp["revenue_loss_usd"], rec["timeline"]["full_recovery_days"]
        readouts([
            {"label": "Production impact", "value": f"{pi['predicted']:.1f}%", "lo": pi["low_p10"], "hi": pi["high_p90"],
             "mid": pi["predicted"], "max": 100, "note": f"likely {pi['low_p10']:.0f}–{pi['high_p90']:.0f}%"},
            {"label": "Revenue loss", "value": money(rl["predicted"]), "lo": rl["low_p10"], "hi": rl["high_p90"],
             "mid": rl["predicted"], "note": f"likely {money(rl['low_p10'])}–{money(rl['high_p90'])}"},
            {"label": "Full recovery", "value": f"{fr['predicted']:.0f} days",
             "note": f"partly back in ~{rec['timeline']['partial_recovery_days']['predicted']:.0f} days"},
            {"label": "Chance of high impact", "value": f"{100 * imp['high_impact_probability']:.0f}%",
             "note": "model estimate: worst quarter of past cases",
             "tone": "rust" if imp["high_impact_probability"] >= 0.5 else ""},
            {"label": "Answer check", "value": f"{j['overall_score']}/5", "tone": "teal" if j["passed"] else "rust",
             "note": "passed the judge" if j["passed"] else "did not pass the judge"},
        ])
        used = st.session_state.get("analysis_overrides") or {}
        if used:
            st.caption("Using your details (override what the agents read from the text): " +
                       ", ".join(f"{OVERRIDE_LABELS[k]} = {'Yes' if v is True else 'No' if v is False else v}" for k, v in used.items()))
            clash = a.get("override_notes") or []
            if clash:
                st.info("Please check: " + "; ".join(clash) + ". Your values were used as entered. "
                        "If an old value was left in by mistake, press 'Clear all details' and analyze again.")
        if a.get("assumptions"):
            st.caption("Assumed: " + "; ".join(a["assumptions"]))
        if plan.get("generated_by") == "template" or j.get("judge") == "heuristic" or a["classification"].get("method") == "rules":
            st.info("Simplified analysis: the language model was not used for part of this result (it is switched off, "
                    "unavailable, or gave an unusable answer). The description was read with keyword rules, the plan comes "
                    "from a template and the quality check is a simple checklist. The numbers, search and ranking are unchanged.")

        t = st.tabs(["Response plan", "Similar cases", "Strategy ranking", "Recovery", "Impact drivers", "Judge", "Agent trace"])
        with t[0]:
            html(f'<div class="subhead" style="font-size:1.45rem; margin-top:14px">Recommended: {plan["recommended_strategy"]}</div>'
                 f'<span class="muted">Written by {html_text(plan.get("generated_by"))}</span>')
            st.markdown(md(plan["rationale"]))
            if plan.get("evidence_note"):
                st.warning(plan["evidence_note"])
            if plan.get("close_call"):
                st.info(plan["close_call"])
            c1, c2 = st.columns(2, gap="large")
            c1.markdown("**Do now**\n" + "\n".join(f"1. {md(x)}" for x in plan.get("immediate_actions", [])))
            c2.markdown("**Recovery plan**\n" + "\n".join(f"- {md(x)}" for x in plan.get("recovery_plan", [])))
            st.markdown("**Risks to watch**\n" + "\n".join(f"- {md(x)}" for x in plan.get("risks", [])))
            if plan.get("fallback_strategy"):
                st.caption(f"Fallback strategy: {plan['fallback_strategy']}. Cited cases: {', '.join(plan.get('cited_cases') or []) or 'none'}")
            st.caption("The strategy is chosen by the scoring system (similar-case outcomes, predictions and feedback); "
                       "the AI only explains it.")
            if plan.get("guardrail_note"):
                st.caption("Output guardrail: " + md(plan["guardrail_note"]))
            if plan.get("fact_sheet"):
                with st.expander("Evidence the AI was given (fact sheet)"):
                    st.markdown(fact_sheet_md(plan["fact_sheet"]))
        with t[1]:
            st.markdown(md(a["investigation"]["historical_summary"]))
            html(filter_chips(a["investigation"]["filters_applied"]))
            st.caption(f"{a['investigation']['total_matching_filters']:,} matching records; the closest are shown below." +
                       (f" {'; '.join(a['investigation']['relaxations'])}" if a['investigation']['relaxations'] else ""))
            cases_table(a["investigation"]["similar_cases"])
        with t[2]:
            if a["response"].get("basis"):
                st.caption(f"Strategies are compared on {a['response']['basis']['description']}. "
                           f"The cases shown in 'Similar cases' are the closest examples from that group.")
            ranking = a["response"]["strategy_ranking"]
            strategy_rows(ranking, plan.get("recommended_strategy"))
            with st.expander("All numbers behind the ranking"):
                rk = pd.DataFrame([{k: v for k, v in r.items() if k not in ("historical", "predicted")} for r in ranking])
                st.dataframe(rk[["rank", "response_type", "strategy_score", "expected_full_recovery_days", "expected_revenue_loss_usd",
                                 "supplier_change_risk", "evidence_cases", "evidence_total", "feedback_multiplier"]],
                             hide_index=True, width="stretch", column_config={
                    "rank": "#", "response_type": "strategy", "strategy_score": st.column_config.NumberColumn("score", format="%.0f"),
                    "expected_full_recovery_days": st.column_config.NumberColumn("recovery days", format="%.0f"),
                    "expected_revenue_loss_usd": st.column_config.NumberColumn("revenue loss", format="$%d"),
                    "supplier_change_risk": st.column_config.NumberColumn("supplier change risk", format="percent"),
                    "evidence_cases": "past cases using it", "evidence_total": "comparable cases",
                    "feedback_multiplier": st.column_config.NumberColumn("feedback weight", format="%.2f")})
        with t[3]:
            subhead("Road to recovery")
            milestone_track(rec["milestones"])
            rs = rec["resilience"]
            readouts([
                {"label": "Chance you'll switch supplier", "value": f"{100 * rec['supplier_change_probability']:.0f}%",
                 "note": rec["supplier_change_outlook"]},
                {"label": "Supplier resilience", "value": f"{rs['resilience_score']}/100 ({rs['resilience_grade']})",
                 "tone": "rust" if rs["resilience_score"] < 45 else "teal" if rs["resilience_score"] >= 75 else "",
                 "note": f"risk band: {rs['risk_band']}"},
            ])
            subhead("Keep an eye on")
            html('<div class="kpis">' + "".join(f"<span>{html_text(k)}</span>" for k in rec["monitoring_kpis"]) + "</div>")
        with t[4]:
            d = a["impact_assessment"]["drivers"]
            c1, c2 = st.columns(2)
            with c1:
                shap_bar(d["full_recovery_days"]["top"], d["full_recovery_days"]["unit"], "What drives recovery time")
            with c2:
                shap_bar(d["production_impact_pct"]["top"], d["production_impact_pct"]["unit"], "What drives production impact")
            for k in d:
                st.caption(d[k]["summary"])
            fc = pd.Series(pr["factor_contributions"]).sort_values()
            fig = go.Figure(go.Bar(x=fc.values, y=fc.index, orientation="h", marker_color=PRIORITY_COLORS.get(pr["priority_level"], TEAL)))
            fig.update_layout(title="How the priority score adds up", xaxis_title="points", bargap=0.35)
            chart(fig, 280)
        with t[5]:
            sc = pd.DataFrame([{"criterion": k, "score": v, "reason": j["reasons"].get(k, "")} for k, v in j["scores"].items()])
            fig = px.bar(sc, x="score", y="criterion", orientation="h", range_x=[0, 5], text="score")
            fig.update_traces(marker_color=TEAL, textposition="outside")
            fig.update_layout(yaxis_title="", bargap=0.35)
            chart(fig, 260)
            with st.expander("Why each criterion got its score"):
                for _, row in sc.iterrows():
                    st.markdown(f"**{str(row['criterion']).replace('_', ' ').capitalize()}: {row['score']}/5**  \n{md(row['reason'])}")
            st.caption(f"Judge: {j['judge']}. Pass mark {j['threshold']}. Revisions made: {a['revisions']}")
            if j.get("overall_feedback"):
                st.info(md(j["overall_feedback"]))
        with t[6]:
            steps = "".join(f'<li class="{"blocked" if s["status"] == "blocked" else "ok"} reveal" style="--i:{i}">'
                            f'<span class="agent">{html_text(s["agent"])}</span><span class="ms">{s["duration_ms"]} ms</span>'
                            f'<p>{html_text(tidy(s["summary"]))}</p></li>' for i, s in enumerate(a["trace"]))
            html(f'<ol class="trace">{steps}</ol>')
            st.caption(f"Total: {a['total_duration_ms'] / 1000:.1f}s")

        st.divider()
        subhead("Was this analysis useful?")
        if st.session_state.get("fb_sent"):
            st.success("Feedback saved. It will shape how strategies are ranked from now on.")
        else:
            with st.form("feedback", border=False):
                c1, c2, c3 = st.columns(3)
                rating = c1.slider("Rating", 1, 5, 4)
                helpful = c2.radio("Helpful?", ["Yes", "No"], horizontal=True)
                chosen = c3.selectbox("Strategy you will actually use", RESPONSES, index=RESPONSES.index(plan["recommended_strategy"])
                                      if plan.get("recommended_strategy") in RESPONSES else 0)
                comment = st.text_input("Comment (optional)")
                if st.form_submit_button("Save feedback"):
                    res = api("POST", "/feedback", {"query": a["query"], "endpoint": "analyze", "rating": rating,
                                                    "helpful": helpful == "Yes", "comment": comment or None,
                                                    "recommended_strategy": plan.get("recommended_strategy"),
                                                    "chosen_strategy": chosen, "cited_cases": plan.get("cited_cases") or [],
                                                    "plan_text": json.dumps(plan)[:4900]})
                    if res:
                        st.session_state["fb_sent"] = True
                        st.rerun()

# ---------------------------------------------------------------- 2. Similar cases
with tabs[1]:
    intro("Search past disruptions", "Find historical cases like yours and see how they were handled. "
          "Hybrid search blends meaning (semantic) with exact terms (keyword).")
    q = st.text_input("Search", "ransomware attack on electronics supplier in Asia", label_visibility="collapsed")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    mode = c1.radio("Retrieval mode", ["hybrid", "semantic", "keyword"], horizontal=True)
    alpha = c2.slider("Semantic weight α", 0.0, 1.0, 0.6, 0.05, disabled=mode != "hybrid")
    top_k = c3.slider("Results", 5, 30, 10)
    c4.write("")
    auto = c4.toggle("Filter by detected type", value=False)
    with st.expander("Filter by type, industry, region and more"):
        f1, f2, f3 = st.columns(3)
        filters = {"disruption_type": f1.multiselect("Type", TYPES), "industry": f2.multiselect("Industry", INDUSTRIES),
                   "supplier_region": f3.multiselect("Region", REGIONS)}
        f1, f2, f3 = st.columns(3)
        filters["supplier_tier"] = f1.multiselect("Tier", [1, 2, 3, 4])
        sev = f2.slider("Severity range", 1, 5, (1, 5))
        filters["response_type"] = f3.multiselect("Response type", RESPONSES)
        if sev != (1, 5):  # only filter when the range is narrowed
            filters["min_severity"], filters["max_severity"] = sev
    if st.button("Search cases", type="primary"):
        payload = {"query": q, "top_k": top_k, "mode": mode, "alpha": alpha, "auto_filter": auto,
                   "filters": {k: v for k, v in filters.items() if v not in ([], None)}}
        wait = st.empty()
        wait.markdown(loader(["Searching 100,000 past cases"]), unsafe_allow_html=True)
        res = api("POST", "/search", payload)
        wait.empty()
        if res:
            html(f'<div class="dispatch reveal">{html_text(res["summary"])}</div>')
            st.caption(f"{res['total_matching_filters']:,} records match the filters, found in {res['latency_ms']} ms. "
                       f"Filters applied: {res['filters_applied']}")
            if res.get("classification"):
                st.caption(f"Detected type: {res['classification']['disruption_type']} ({res['classification']['method']})")
            cases_table(res["results"])
            with st.expander("Read the case narratives"):
                for c in res["results"]:
                    st.markdown(f"**{c['disruption_id']}**: {md(c['narrative'])}")

# ---------------------------------------------------------------- 3. Prioritize
with tabs[2]:
    intro("Rank open disruptions", "Scores combine severity, production impact, financial loss, supplier tier and "
          "whether a backup exists. Edit the table, add rows, then rank.")
    default = pd.DataFrame([
        {"id": "Typhoon – Taiwan chips", "disruption_severity": 4, "production_impact_pct": 60.0, "revenue_loss_usd": 8_000_000, "supplier_tier": 1, "has_backup_supplier": False},
        {"id": "Port backlog – Rotterdam", "disruption_severity": 2, "production_impact_pct": 18.0, "revenue_loss_usd": 400_000, "supplier_tier": 2, "has_backup_supplier": True},
        {"id": "Ransomware – Tier 3", "disruption_severity": 3, "production_impact_pct": 35.0, "revenue_loss_usd": 1_500_000, "supplier_tier": 3, "has_backup_supplier": False},
        {"id": "Strike – Mexico plant", "disruption_severity": 3, "production_impact_pct": 42.0, "revenue_loss_usd": 2_200_000, "supplier_tier": 1, "has_backup_supplier": True},
        {"id": "Tariffs – packaging", "disruption_severity": 1, "production_impact_pct": 6.0, "revenue_loss_usd": 90_000, "supplier_tier": 4, "has_backup_supplier": True},
    ])
    edited = st.data_editor(default, num_rows="dynamic", width="stretch", hide_index=True, column_config={
        "id": "disruption",
        "disruption_severity": st.column_config.NumberColumn("severity", min_value=1, max_value=5, step=1),
        "production_impact_pct": st.column_config.NumberColumn("impact %", min_value=0, max_value=100),
        "revenue_loss_usd": st.column_config.NumberColumn("revenue loss", min_value=0, format="$%d"),
        "supplier_tier": st.column_config.SelectboxColumn("tier", options=[1, 2, 3, 4]),
        "has_backup_supplier": "backup supplier"})
    if st.button("Rank disruptions", type="primary"):
        items = edited.dropna().to_dict("records")
        for it in items:
            it["supplier_tier"] = int(it["supplier_tier"]); it["disruption_severity"] = int(it["disruption_severity"])
        res = api("POST", "/prioritize", {"items": items})
        if res:
            top = max((r["priority_score"] for r in res["ranked"]), default=1) or 1
            rows = "".join(
                f'<div class="row reveal" style="--i:{i}"><span class="rank">{r["rank"]}</span>'
                f'{badge(r["priority_level"], r["priority_label"], r["priority_score"])}'
                f'<div class="what"><b>{html_text(r["id"])}</b><span>{html_text(r["recommended_action"])}</span></div>'
                f'<div class="meter" style="--c:{PRIORITY_COLORS.get(r["priority_level"], TEAL)}">'
                f'<i style="width:{100 * r["priority_score"] / top:.0f}%"></i></div></div>'
                for i, r in enumerate(res["ranked"]))
            html(f'<div class="ranked">{rows}</div>')
            contrib = pd.DataFrame([{"id": r["id"], **r["factor_contributions"]} for r in res["ranked"]])
            fig = px.bar(contrib.melt(id_vars="id", var_name="factor", value_name="points"), x="points", y="id",
                         color="factor", orientation="h", title="What each score is made of")
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, yaxis_title="", bargap=0.35,
                              legend=dict(orientation="h", y=-0.2))
            chart(fig, 340)

# ---------------------------------------------------------------- 4. Predict & Explain
with tabs[3]:
    intro("Predict impact and explain it", "Estimate production impact, financial loss and recovery time for a "
          "disruption profile, compare response strategies, and see which factors move the numbers.")
    prof = profile_form("pred", with_response=True)
    c1, c2 = st.columns([1, 1])
    target = c1.selectbox("Explain this prediction", ["full_recovery_days", "production_impact_pct", "revenue_loss_usd",
                                                      "partial_recovery_days", "high_impact", "permanent_supplier_change"])
    c2.write("")
    narrate = c2.toggle("Add a plain-language explanation (LLM)", value=False)
    if st.button("Predict and explain", type="primary"):
        wait = st.empty()
        wait.markdown(loader(["Running the impact models"]), unsafe_allow_html=True)
        pr = api("POST", "/predict", prof)
        ex_res = api("POST", "/explain", {"profile": prof, "target": target, "narrate": narrate})
        wait.empty()
        if pr and ex_res:
            p = pr["predictions"]
            pi, rl, fr = p["production_impact_pct"], p["revenue_loss_usd"], p["full_recovery_days"]
            readouts([
                {"label": "Production impact", "value": f"{pi['predicted']:.1f}%", "lo": pi["low_p10"], "hi": pi["high_p90"],
                 "mid": pi["predicted"], "max": 100, "note": f"likely {pi['low_p10']:.0f}–{pi['high_p90']:.0f}%"},
                {"label": "Revenue loss", "value": money(rl["predicted"]), "lo": rl["low_p10"], "hi": rl["high_p90"],
                 "mid": rl["predicted"], "note": f"likely {money(rl['low_p10'])}–{money(rl['high_p90'])}"},
                {"label": "Full recovery", "value": f"{fr['predicted']:.0f} days", "lo": fr["low_p10"], "hi": fr["high_p90"],
                 "mid": fr["predicted"], "note": f"likely {fr['low_p10']:.0f}–{fr['high_p90']:.0f} days"},
                {"label": "Chance of high impact", "value": f"{100 * p['high_impact_probability']:.0f}%",
                 "tone": "rust" if p["high_impact_probability"] >= 0.5 else ""},
                {"label": "Chance of switching supplier", "value": f"{100 * p['supplier_change_probability']:.0f}%"},
            ])
            c1, c2 = st.columns(2)
            with c1:
                wi = pd.DataFrame(pr["what_if_by_response"])
                fig = px.bar(wi, x="predicted_full_recovery_days", y="response_type", orientation="h",
                             title="What if you respond differently? Days to full recovery", color="predicted_full_recovery_days",
                             color_continuous_scale=RISK_SCALE, labels={"predicted_full_recovery_days": "days"})
                fig.update_layout(yaxis={"categoryorder": "total descending"}, coloraxis_showscale=False,
                                  yaxis_title="", bargap=0.35)
                chart(fig, 320)
            with c2:
                shap_bar(ex_res["contributions"], ex_res["unit"], f"Why? Drivers of {target.replace('_', ' ')}")
            html(f'<div class="dispatch reveal">{html_text(ex_res.get("narrative") or ex_res["summary"])}</div>')

# ---------------------------------------------------------------- 5. Risk & Resilience
with tabs[4]:
    intro("Score a supplier's resilience", "How well would this supplier absorb a disruption, and how likely is one "
          "to turn high-impact? Every disruption type is weighed by how often it has happened.")
    c1, c2, c3 = st.columns(3)
    rp = {"industry": c1.selectbox("Industry", INDUSTRIES, key="ri"), "supplier_region": c2.selectbox("Region", REGIONS, key="rr"),
          "supplier_tier": c3.selectbox("Tier", [1, 2, 3, 4], key="rt")}
    c1, c2, c3 = st.columns(3)
    rp["supplier_size"] = c1.selectbox("Size", SIZES, index=1, key="rs")
    rp["assumed_severity"] = c2.slider("Assumed severity", 1, 5, 3, key="rsev")
    c3.write("")
    rp["has_backup_supplier"] = c3.toggle("Backup supplier available", key="rb")
    if st.button("Score resilience", type="primary"):
        r = api("POST", "/risk", rp)
        if r:
            c1, c2 = st.columns([1, 2], gap="large")
            with c1:
                fig = go.Figure(go.Indicator(mode="gauge+number", value=r["resilience_score"],
                                             number={"font": {"size": 46, "color": INK}},
                                             title={"text": f"Resilience, grade {r['resilience_grade']}", "font": {"size": 15}},
                                             gauge={"axis": {"range": [0, 100], "tickcolor": FOG, "tickfont": {"color": MUTED}},
                                                    "bar": {"color": INK, "thickness": 0.28}, "borderwidth": 0,
                                                    "steps": [{"range": [0, 45], "color": "#EBCFC8"},
                                                              {"range": [45, 75], "color": "#F3E3B5"},
                                                              {"range": [75, 100], "color": "#C6DEDA"}]}))
                fig.update_layout(margin=dict(t=50, b=10, l=20, r=20), height=260, paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
                st.metric("Chance a disruption turns high-impact", f"{100 * r['disruption_risk_probability']:.0f}%", r["risk_band"],
                          delta_color="off", delta_arrow="off")
            with c2:
                ex_df = pd.DataFrame(r["exposure_by_type"])
                fig = px.bar(ex_df, x="disruption_type", y="vulnerability", color="historical_frequency",
                             title="Where this supplier is exposed", color_continuous_scale=SEA_SCALE,
                             labels={"disruption_type": "", "historical_frequency": "how often"},
                             hover_data=["predicted_full_recovery_days", "high_impact_probability"])
                fig.update_layout(bargap=0.4)
                chart(fig, 320)
            st.markdown("**Recommendations**\n" + "\n".join(f"- {md(x)}" for x in r["recommendations"]))
            shap_bar(r["top_risk_drivers"], "log-odds", "What raises or lowers the risk")

# ---------------------------------------------------------------- 6. Insights & Evaluation
with tabs[5]:
    s = api("GET", "/stats")
    ins = api("GET", "/insights")
    if s and ins:
        t = s["totals"]
        intro(f"What {s['total_records']:,} past disruptions show", "Patterns across the historical record and how well "
              "the models predict. Test results are on the Evaluation tab.")
        readouts([
            {"label": "Disruptions on record", "value": f"{s['total_records']:,}"},
            {"label": "Average production impact", "value": f"{t['avg_production_impact_pct']}%"},
            {"label": "Median full recovery", "value": f"{t['median_full_recovery_days']:.0f} days"},
            {"label": "Had a backup supplier", "value": f"{100 * t['backup_supplier_rate']:.0f}%"},
            {"label": "Switched supplier for good", "value": f"{100 * t['permanent_supplier_change_rate']:.0f}%"},
        ])
        subhead("Key findings")
        for line in ins["key_insights"]:
            st.markdown(f"- {md(line)}")
        c1, c2 = st.columns(2)
        with c1:
            sev = pd.DataFrame(s["by_severity"]).T.reset_index(names="severity")
            fig = px.line(sev, x="severity", y=["avg_production_impact_pct", "avg_full_recovery_days"], markers=True,
                          title="Impact and recovery rise with severity")
            fig.update_traces(line_width=2.5, marker_size=8)
            fig.update_layout(legend=dict(orientation="h", y=-0.2), yaxis_title="")
            chart(fig, 330)
        with c2:
            heat = pd.DataFrame(s["recovery_days_by_type_and_response"]).T
            fig = px.imshow(heat, text_auto=".0f", color_continuous_scale=HEAT_SCALE, aspect="auto",
                            title="Average days to full recovery, by type and response")
            chart(fig, 330)
        c1, c2 = st.columns(2)
        with c1:
            tgt = st.selectbox("What drives this outcome?", list(ins["global_importance"].keys()))
            gi = pd.DataFrame(ins["global_importance"][tgt])
            fig = px.bar(gi, x="share_pct", y="label", orientation="h", labels={"share_pct": "share of influence (%)"})
            fig.update_traces(marker_color=TEAL)
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, yaxis_title="", bargap=0.35)
            chart(fig, 330)
        with c2:
            subhead("Prediction models, tested on 20% held-out data")
            mm = pd.DataFrame(ins["model_metrics"]).T
            st.dataframe(mm[mm["R2"].notna()][["MAE", "RMSE", "R2", "baseline_MAE", "interval_coverage_p10_p90"]], width="stretch")
            subhead("Risk classifiers")
            cols = [c for c in ["ROC_AUC", "PR_AUC", "threshold", "precision", "recall", "F1", "accuracy", "positive_rate"] if c in mm]
            st.dataframe(mm[mm["ROC_AUC"].notna()][cols], width="stretch")
            st.caption("F1, precision and recall use a cutoff tuned on training data (a 0.5 cutoff almost never flags the rarer "
                       "outcome). ROC-AUC and PR-AUC don't depend on the cutoff. Supplier change has weak signal in the data.")

        subhead("Feedback loop")
        fb = api("GET", "/feedback/stats")
        if fb and fb["total_feedback"]:
            m = st.columns(3)
            m[0].metric("Feedback received", fb["total_feedback"])
            m[1].metric("Average rating", fb["average_rating"])
            m[2].metric("Found it helpful", f"{100 * (fb['helpful_rate'] or 0):.0f}%")
            if fb["strategy_multipliers"]:
                st.caption("Learned strategy weights (applied to rankings): " +
                           ", ".join(f"{k} ×{v}" for k, v in fb["strategy_multipliers"].items()))
            st.dataframe(pd.DataFrame(fb["recent"]), hide_index=True, width="stretch")
        else:
            st.caption("No feedback yet. Rate an analysis on the Analyze tab to start the loop.")


# ---------------------------------------------------------------- 7. Evaluation
FRAMEWORK_METRICS = {
    "answer_relevancy": ("Answer relevancy", "Does the plan answer the question that was asked?"),
    "faithfulness": ("Faithfulness", "Does every claim stick to the evidence it was given?"),
    "faithfulness_explanation": ("Faithfulness (explanation only)", "The same check on the written rationale alone, without action steps."),
    "contextual_precision": ("Context precision", "Were the most useful cases ranked first?"),
    "context_precision": ("Context precision", "Were the most useful cases ranked first?"),
    "contextual_recall": ("Context recall", "Did the evidence cover what the reference answer says?"),
    "context_recall": ("Context recall", "Did the evidence cover what the reference answer says?"),
    "recommendation_quality": ("Recommendation quality", "Does the chosen strategy match the reference strategy?"),
    "analysis_correctness": ("Analysis correctness", "Are the numbers and reasoning in the analysis right?"),
}


def hbars(rows: list[tuple[str, float, str]], xmax: float, fmt, height: int | None = None):
    """Small labelled horizontal bars: rows of (label, value, colour)."""
    df = pd.DataFrame(rows, columns=["label", "value", "color"])
    fig = go.Figure(go.Bar(x=df["value"], y=df["label"], orientation="h", marker_color=df["color"],
                           text=[fmt(v) for v in df["value"]], textposition="outside", cliponaxis=False))
    fig.update_layout(xaxis=dict(range=[0, xmax * 1.18], visible=False), yaxis=dict(autorange="reversed", title=""),
                      bargap=0.35, showlegend=False)
    chart(fig, height or 34 * len(rows) + 24)


def eval_card(title: str, big: str, meaning: str):
    st.markdown(f"**{title}** &nbsp; :green-badge[Strong]")
    st.markdown(f"### {big}")
    st.caption(meaning)


with tabs[6]:
    intro("How well does it work?", "The results of every test we ran, the strong ones first. Where a number is weaker, "
          "we say why.")
    ev = api("GET", "/evaluation") or {}
    mm, se = ev.get("model_metrics"), ev.get("search_eval")
    de, rg, jd = ev.get("deepeval_results"), ev.get("ragas_results"), ev.get("llm_judge_eval")
    cl = (ev.get("classification_eval") or {}).get("results", {})
    if not (mm and se and de and rg and jd and cl.get("llm_agent")):
        st.info("The evaluation results could not be loaded. Make sure the API is running and that "
                "`python -m scripts.run_evaluation` has produced results.")
    else:
        loose, strict = "loose (type + industry)", "strict (type + industry + severity +/-1)"
        hy, kw, sm = se["results"]["hybrid a=0.6 (default)"], se["results"]["keyword"], se["results"]["semantic"]
        llm = cl["llm_agent"]
        llm_acc = min(llm["accuracy"].values())
        judge_name = str(jd.get("judge_model") or "the judge model").replace("claude-sonnet-5-5", "Claude Sonnet 5.5")
        regs = (("production_impact_pct", "Production impact"), ("revenue_loss_usd", "Revenue loss"),
                ("full_recovery_days", "Full recovery time"), ("partial_recovery_days", "Partial recovery time"))
        cover = [mm[k]["interval_coverage_p10_p90"] for k, _ in regs]
        NAVY, GREY, MID, GREEN = "#14506B", "#9FB0BB", "#1D7A9E", "#2E7D5B"

        readouts([
            {"label": "Spots high-impact disruptions", "value": f"{mm['high_impact']['ROC_AUC']:.2f}", "note": "ROC-AUC, on data it never saw"},
            {"label": "Finds the right past cases", "value": f"{hy[loose]['precision@10'] * 10:.1f} / 10", "note": f"{se['n_queries']} test searches"},
            {"label": "Understands your description", "value": f"{llm_acc:.0%}", "note": "type, industry, region, tier, backup"},
            {"label": "Answers stay true to the evidence", "value": f"{de['summary']['faithfulness']['mean']:.2f}", "note": "DeepEval faithfulness"},
        ])
        st.caption(f"Every score below was produced by tests we ran on this system. The language-model grading was done "
                   f"with {judge_name}.")

        subhead("What it does well")
        r1 = st.columns(3)
        with r1[0], st.container(border=True):
            eval_card("Spots high-impact disruptions", f"{mm['high_impact']['ROC_AUC']:.2f} ROC-AUC",
                      "Given a disruption, it ranks the ones that will hurt most far above the rest. 0.5 would be a coin "
                      "toss and 1.0 perfect.")
            hbars([("Precision", mm["high_impact"]["precision"], NAVY), ("Recall", mm["high_impact"]["recall"], NAVY),
                   ("F1 score", mm["high_impact"]["F1"], GREEN)], 1, lambda v: f"{v:.2f}")
        with r1[1], st.container(border=True):
            p = mm["production_impact_pct"]
            eval_card("Predicts production impact", f"{p['R2']:.2f} R²",
                      f"It is off by {p['MAE']:.1f} percentage points on average. Guessing the average would be off by "
                      f"{p['baseline_MAE']:.1f}.")
            hbars([("Our model", p["MAE"], NAVY), ("Guessing the average", p["baseline_MAE"], GREY)],
                  p["baseline_MAE"], lambda v: f"{v:.1f} pts")
        with r1[2], st.container(border=True):
            eval_card("Honest ranges", f"{min(cover):.0%} to {max(cover):.0%} inside",
                      "Every estimate comes with a likely range. The real answer landed inside it about 4 times in 5, as "
                      "intended (the target is 80%).")
            hbars([(n, mm[k]["interval_coverage_p10_p90"], MID) for k, n in regs], 1, lambda v: f"{v:.0%}")
        r2 = st.columns(3)
        with r2[0], st.container(border=True):
            eval_card("Finds the right past cases", f"{hy[loose]['precision@10'] * 10:.1f} of 10",
                      f"Of the top 10 cases, this many have the right disruption type and industry. The very first result "
                      f"is right {hy[loose]['hit@1']:.0%} of the time.")
            hbars([("Keywords only", kw[loose]["precision@10"] * 10, GREY), ("Meaning only", sm[loose]["precision@10"] * 10, MID),
                   ("Hybrid (default)", hy[loose]["precision@10"] * 10, NAVY)], 10, lambda v: f"{v:.1f}")
        with r2[1], st.container(border=True):
            eval_card("Understands your description", f"{llm_acc:.0%}",
                      "Reading a plain-English description, it got the disruption type, industry, region, supplier tier and "
                      "backup status right every time, and its severity guess was never more than 1 off.")
            hbars([(n, llm["accuracy"][k], NAVY) for k, n in
                   (("disruption_type", "Disruption type"), ("industry", "Industry"), ("supplier_region", "Region"),
                    ("supplier_tier", "Tier"), ("has_backup_supplier", "Backup supplier"))], 1, lambda v: f"{v:.0%}")
        with r2[2], st.container(border=True):
            d = de["summary"]
            eval_card("Relevant, grounded answers", f"{d['answer_relevancy']['mean']:.2f} relevancy",
                      "The written plans answer the question that was asked and stick to the evidence they were given. "
                      + ("Every plan also passed the built-in quality check." if jd["pass_rate"] >= 1 else
                         f"{jd['pass_rate']:.0%} of plans also passed the built-in quality check."))
            hbars([("Answer relevancy", d["answer_relevancy"]["mean"], NAVY), ("Faithfulness", d["faithfulness"]["mean"], NAVY),
                   ("Context precision", d["contextual_precision"]["mean"], NAVY),
                   ("Analysis correctness", d["analysis_correctness"]["mean"], NAVY)], 1, lambda v: f"{v:.2f}")
            st.markdown(f"**{jd['mean_overall']:.2f} / 5** average judge score, **{jd['pass_rate']:.0%}** pass rate")

        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**Search, with the harder test**")
            st.caption("Counting a result as right only if the severity is within one level as well.")
            hbars([("Keywords only", kw[strict]["precision@10"] * 10, GREY), ("Meaning only", sm[strict]["precision@10"] * 10, MID),
                   ("Hybrid (default)", hy[strict]["precision@10"] * 10, NAVY)], 10, lambda v: f"{v:.1f} of 10")
        with c2, st.container(border=True):
            st.markdown("**What the judge scored, out of 5**")
            st.caption(f"Five criteria on {jd['n_cases']} full plans.")
            crit = sorted(jd["mean_by_criterion"].items(), key=lambda kv: -kv[1])
            hbars([(k.capitalize(), v, GREEN if v >= 4.5 else NAVY) for k, v in crit], 5, lambda v: f"{v:.1f}")

        subhead("DeepEval and RAGAS, side by side")
        st.caption(f"Two independent toolkits grade the same {de['n_cases']} plans. They ask different questions, so their "
                   "scores are shown apart and never averaged.")
        fw = st.columns(2)
        for col, name, blurb, data in ((fw[0], "DeepEval", "Grades answer, evidence and strategy", de),
                                       (fw[1], "RAGAS", "Checks claims one by one against the evidence", rg)):
            with col, st.container(border=True):
                st.markdown(f"**{name}** · {blurb}")
                st.caption(f"{data['n_cases']} scenarios · judge: {judge_name}")
                for k, v in data["summary"].items():
                    label, hint = FRAMEWORK_METRICS.get(k, (k.replace("_", " "), ""))
                    st.progress(min(max(v["mean"], 0.0), 1.0), text=f"{label}: **{v['mean']:.2f}**")
                    if hint:
                        st.caption(hint)

        subhead("Where it is weaker")
        weak = [
            ("Revenue loss", "Data limit", f"R² {mm['revenue_loss_usd']['R2']:.2f}",
             "Depends on company size, which is not in the data. Shown as a range."),
            ("Recovery time", "Data limit", f"R² {mm['full_recovery_days']['R2']:.2f} / {mm['partial_recovery_days']['R2']:.2f}",
             "Local details are not recorded, and three different algorithms score the same."),
            ("Supplier replaced?", "Data limit", f"AUC {mm['permanent_supplier_change']['ROC_AUC']:.2f}",
             "Barely tied to the recorded facts, so a weak signal."),
            ("RAGAS faithfulness", "Strict test", f"{rg['summary']['faithfulness']['mean']:.2f} / "
             f"{rg['summary']['faithfulness_explanation']['mean']:.2f}",
             "Action steps count as unsupported claims. The explanation alone scores higher."),
        ]
        with st.container(border=True):
            for title, tag, big, why in weak:
                a, b, c = st.columns([2.2, 1.3, 4])
                tag_md = ":orange-badge[Data limit]" if tag == "Data limit" else ":blue-badge[Strict test]"
                a.markdown(f"**{title}** &nbsp; {tag_md}")
                b.markdown(f"**{big}**")
                c.caption(why)

        with st.expander("Detailed tables"):
            if "retrieval_eval" in ev:
                rv = pd.DataFrame(ev["retrieval_eval"]["results"]).T.reset_index(names="retriever")
                fig = px.bar(rv.melt(id_vars="retriever", value_vars=["precision@10", "MRR", "nDCG@10"]), x="variable",
                             y="value", color="retriever", barmode="group",
                             title=f"Retrieval quality on {ev['retrieval_eval']['n_queries']} golden scenarios")
                fig.update_layout(xaxis_title="", yaxis_title="", legend=dict(orientation="h", y=-0.15))
                chart(fig, 340)
            subhead("Classification accuracy")
            st.dataframe(pd.DataFrame({k: {**v["accuracy"], "severity_MAE": v["severity_MAE"]} for k, v in cl.items()}),
                         width="stretch")
