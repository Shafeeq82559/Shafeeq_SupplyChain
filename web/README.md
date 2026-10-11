# Disruption Assistant: React frontend

A Vite + React + TypeScript dashboard for the Supply Chain Disruption Assistant API. The Streamlit app (`frontend.py`)
calls the same API and remains available.

## Run

Start the backend from the repo root, then the web app:

```bash
.venv/Scripts/python.exe -m uvicorn src.main:app --port 8000
npm --prefix web install
npm --prefix web run dev
```

Open http://localhost:5173. The dev server forwards `/api/*` to the backend at `127.0.0.1:8000` (see `vite.config.ts`).
The API needs about 30 to 60 seconds after a restart to load its index and models; the status panel shows when it's ready.

## What is built

- **Landing hero**: the title animates in over drifting trade routes; scrolling brings the "What happened?" composer up into view.
- **Side rails (every page, wide screens)**: a port scene on the left and a route network with page facts on the right stay in view while
  you scroll and react to it: the crane works, containers stack up, the ship sails, a container travels the route, and a ring shows how far
  down the page you are.
- **Analyze**: examples, optional known details, and a live agent pipeline fed by `POST /analyze/stream` (each agent is reported as
  it finishes, so progress and timings are real). Results: priority ring, recommended response, KPI cards with p10 to p90 ranges,
  then tabs for plan, similar cases, strategy ranking, recovery, impact drivers, judge and agent trace, plus a feedback form.
- **Report and history**: every briefing can be downloaded as a standalone HTML report, saved as PDF (print dialog) or exported as
  JSON. Each analysis is saved on this device (up to 15) and can be reopened from the History drawer without re-running it.
- **Similar cases**: hybrid, semantic or keyword search with filters; results as cards with score bars and narratives.
- **Prioritize**: editable table, ranked list, priority map (bubble chart) and score breakdowns.
- **Predict & explain**: estimates with ranges, a what-if per strategy, and a waterfall from the average case to this one.
- **Risk & resilience**: resilience and risk gauges, exposure radar, recommendations and risk drivers.
- **Insights**: dataset patterns (line charts, heatmap, bars), model quality, evaluation results and the feedback loop.
- **Light and dark themes**: a sun/moon button in the top bar. It starts from your system setting, remembers your choice, and is applied before first paint so there is no flash. All colours are tokens in `src/index.css` (`:root` and `:root[data-theme='dark']`), so charts, SVG art and components follow the theme.
- A shareable link: `?q=<description>` runs the analysis on load. The top bar shows system status and switches the language model.

## Structure

```
src/api.ts             typed client, response types, NDJSON stream reader
src/lib.ts             constants, formatters, count-up hook
src/history.ts         saved analyses (localStorage store)
src/report.ts          standalone HTML report builder, download and print helpers
src/App.tsx            shell, health polling, hash routing
src/pages/             Analyze, Cases, Prioritize, Predict, Risk, Insights
src/components/        Nav, Hero, Pipeline, Results, Tabs, Feedback, HistoryDrawer, ReportMenu, SideRails,
                       charts + chartkit (gauge, radar, line, heatmap, waterfall, bubble, bars), Kpi, ui (form controls), motionkit
src/index.css, pages.css   design tokens and styles
```

The whole app ships about 127 KB gzipped (no chart library).
