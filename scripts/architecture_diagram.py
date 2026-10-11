"""Render the architecture diagram to architecture/Architecture_Diagram.pdf and .png (matplotlib).

One left-to-right request flow (UI -> FastAPI gateway -> LangGraph agents -> report), the services the agents use
(hybrid retriever, ML models, LLM), the feedback loop, and the offline build lane. Together this covers the chain the
submission guidelines ask for: Dataset -> Preprocessing -> Chunking -> Embeddings -> Vector DB -> Retriever ->
LLM / RAG pipeline -> Agents -> API layer -> User interface.

Usage:  python -m scripts.architecture_diagram
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "architecture"
FONT = "Segoe UI" if any(f.name == "Segoe UI" for f in font_manager.fontManager.ttflist) else "DejaVu Sans"
plt.rcParams["font.family"] = FONT

INK, MUTED, LINE = "#16323F", "#5B7380", "#2B5566"
NAVY, TEAL, SKY = "#14506B", "#1D7A9E", "#E9F3F6"
AMBER, AMBER_BG = "#B7791F", "#FDF6E9"
GREEN, GREEN_BG = "#2E7D5B", "#EAF5EF"
PLUM, PLUM_BG = "#6B4C9A", "#F2EEF8"
GREY_BG = "#F4F6F8"


def box(ax, x, y, w, h, title, sub="", kicker="", edge=NAVY, fill="white", lw=1.6, title_fs=12.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.16", fc=fill, ec=edge, lw=lw, zorder=3))
    cx, extra = x + w / 2, title.count("\n")
    if not sub and not kicker:
        ax.text(cx, y + h / 2, title, ha="center", va="center", fontsize=title_fs, fontweight="bold", color=INK, zorder=4)
        return
    top = y + h - 0.3
    if kicker:
        ax.text(cx, top, kicker, ha="center", va="center", fontsize=8.3, color=edge, fontweight="bold", zorder=4)
        top -= 0.38
    ax.text(cx, top, title, ha="center", va="top", fontsize=title_fs, fontweight="bold", color=INK, linespacing=1.05, zorder=4)
    if sub:
        ax.text(cx, top - 0.42 - 0.24 * extra, sub, ha="center", va="top", fontsize=8.6, color=MUTED, linespacing=1.3, zorder=4)


def arrow(ax, p1, p2, color=LINE, ls="-", rad=0.0, lw=1.6, label="", lxy=None, head=12):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=head, lw=lw, color=color, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0, zorder=2))
    if label:
        x, y = lxy or ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        ax.text(x, y, label, ha="center", va="center", fontsize=8.4, color=color, style="italic", zorder=5,
                bbox=dict(fc="white", ec="none", pad=1.5))


def panel(ax, x, y, w, h, label, edge, fill, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.25", fc=fill, ec=edge, lw=1.3,
                                linestyle=ls, zorder=1))
    ax.text(x + 0.25, y + h - 0.28, label, ha="left", va="center", fontsize=9.5, fontweight="bold", color=edge, zorder=4)


def main():
    H = 11.6
    fig, ax = plt.subplots(figsize=(24, H))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 24); ax.set_ylim(0, H); ax.axis("off")

    ax.text(0.35, 11.1, "Supply Chain Disruption Assistant", ha="left", fontsize=25, fontweight="bold", color=NAVY)
    ax.text(0.37, 10.62, "MULTI-AGENT ARCHITECTURE  ·  HYBRID RAG  ·  ML IMPACT PREDICTION  ·  LLM-AS-JUDGE", ha="left",
            fontsize=10.5, color=TEAL, fontweight="bold")

    # ---------------- request flow
    ry, rh = 5.85, 1.7                                    # agent row
    box(ax, 0.35, ry, 2.15, rh, "Web UI", "React dashboard\nor Streamlit", kicker="INPUT")
    box(ax, 3.0, ry - 0.3, 2.3, rh + 0.6, "FastAPI", "Input guardrails:\ninjection · PII · off-topic\nschema validation",
        kicker="API GATEWAY")
    arrow(ax, (2.5, ry + rh / 2), (3.0, ry + rh / 2))

    panel(ax, 5.8, 5.4, 15.0, 4.2, "LANGGRAPH MULTI-AGENT WORKFLOW  ·  shared typed state", TEAL, SKY)
    agents = [("Classification", "type · industry · region\ntier · backup · severity"),
              ("Investigation", "finds similar past\ncases (hybrid RAG)"),
              ("Impact\nAssessment", "impact · loss · P1-P4"),
              ("Response\nPlanning", "ranks strategies · plan"),
              ("Recovery\nAnalysis", "timeline · resilience"),
              ("Judge", "LLM-as-Judge\n5 criteria, pass/fail")]
    aw, gap, ax0 = 2.05, 0.43, 6.1
    centers = []
    for i, (name, sub) in enumerate(agents):
        x = ax0 + i * (aw + gap)
        box(ax, x, ry, aw, rh, name, sub, kicker=f"0{i + 1}", edge=TEAL, title_fs=11.5 if "\n" in name else 12.5)
        centers.append(x + aw / 2)
        if i:
            arrow(ax, (x - gap, ry + rh / 2), (x, ry + rh / 2), color=TEAL)
    arrow(ax, (5.3, ry + rh / 2), (ax0, ry + rh / 2))
    left = lambda i: ax0 + i * (aw + gap)  # noqa: E731

    # judge -> response revision loop (above the row, between the two boxes)
    arrow(ax, (left(5) + 0.45, ry + rh), (left(3) + aw - 0.45, ry + rh), color=AMBER, ls=(0, (4, 3)), rad=0.3, lw=1.7)
    ax.text((left(3) + left(5) + aw) / 2, ry + rh + 0.72, "SELF-CHECK LOOP  ·  score < 3.5 → revise the plan once",
            ha="center", fontsize=9, color=AMBER, fontweight="bold", zorder=5)

    # LLM strip inside the container
    sy = 8.55
    ax.add_patch(FancyBboxPatch((left(0), sy), left(5) + aw - left(0), 0.55, boxstyle="round,pad=0,rounding_size=0.12",
                                fc=PLUM_BG, ec=PLUM, lw=1.3, zorder=3))
    ax.text(left(0) + 0.2, sy + 0.275, "LLM  ·  Claude Sonnet 5.5", ha="left", va="center", fontsize=10.5, fontweight="bold",
            color=PLUM, zorder=4)
    ax.text(left(5) + aw - 0.2, sy + 0.275, "OpenAI-compatible, provider can be switched  ·  rule / template fallback",
            ha="right", va="center", fontsize=8.8, color=PLUM, zorder=4)
    for i, dx in ((0, 0), (3, -0.55), (5, 0.55)):
        arrow(ax, (centers[i] + dx, sy), (centers[i] + dx, ry + rh), color=PLUM, ls=(0, (2, 2)), lw=1.3, head=10)

    # output
    box(ax, 21.25, ry - 0.15, 2.45, rh + 0.3, "Disruption\nReport", "priority · impact ranges\nplan · recovery · judge",
        kicker="OUTPUT", edge=NAVY, fill="#F1F7FA", lw=2.2)
    arrow(ax, (left(5) + aw, ry + rh / 2), (21.25, ry + rh / 2))
    ax.text(22.47, ry - 0.42, "streamed live to the UI", ha="center", fontsize=8.4, color=MUTED, style="italic")

    # direct tools (dotted, like a side door from the gateway)
    box(ax, 15.6, 9.78, 8.1, 1.05, "Direct tools", "search cases · predict & explain · prioritize · risk & resilience · insights",
        edge=NAVY)
    dy = 10.3
    ax.plot([4.15, 4.15, 15.3], [ry + rh + 0.3, dy, dy], color=LINE, lw=1.4, ls=(0, (2, 3)), zorder=2)
    arrow(ax, (15.3, dy), (15.6, dy), color=LINE)
    ax.text(9.8, dy + 0.17, "direct requests (no agent run)", ha="center", fontsize=8.6, color=MUTED, style="italic")

    # ---------------- services the agents use
    by, bh = 3.25, 1.5
    box(ax, 6.4, by, 4.0, bh, "Hybrid Retriever", "BM25 + vector search · RRF · metadata filters",
        kicker="KNOWLEDGE BASE", edge=GREEN, fill=GREEN_BG)
    arrow(ax, (centers[1], by + bh), (centers[1], ry), color=GREEN)
    box(ax, 11.6, by, 4.3, bh, "ML Models", "LightGBM (P10-P90) · risk classifiers · SHAP",
        kicker="PREDICTION", edge=GREEN, fill=GREEN_BG)
    arrow(ax, (12.9, by + bh), (centers[2], ry), color=GREEN)
    arrow(ax, (14.6, by + bh), (centers[4] - 0.3, ry), color=GREEN)
    box(ax, 18.0, by, 4.4, bh, "Feedback Loop", "ratings → strategy weights · retraining",
        kicker="LEARNING", edge=AMBER, fill=AMBER_BG)
    arrow(ax, (22.47, ry - 0.6), (21.6, by + bh), color=AMBER, ls=(0, (4, 3)))
    arrow(ax, (18.0, by + bh / 2), (15.9, by + bh / 2), color=AMBER, ls=(0, (4, 3)))

    # ---------------- offline build lane
    panel(ax, 0.35, 0.1, 23.35, 2.5, "OFFLINE  ·  BUILT ONCE  (build_index.py, train_models.py)", MUTED, GREY_BG, ls=(0, (5, 3)))
    oy, oh, ow = 0.62, 1.3, 3.05
    steps = [("Dataset", "Kaggle CSV · 100k rows"),
             ("Preprocessing", "clean · derive features"),
             ("Chunking", "1 record = 1 narrative"),
             ("Embeddings", "all-MiniLM-L6-v2"),
             ("Vector DB + BM25", "ChromaDB + keyword index")]
    xs = [0.75, 4.35, 7.95, 11.55, 15.15]
    for (t, s), x in zip(steps, xs):
        box(ax, x, oy, ow, oh, t, s, edge=MUTED, title_fs=12)
    for a, b in zip(xs, xs[1:]):
        arrow(ax, (a + ow, oy + oh / 2), (b, oy + oh / 2), color=MUTED)
    box(ax, 19.75, oy, 3.55, oh, "Model Training", "LightGBM + SHAP", edge=MUTED, title_fs=12)
    fx, tx, ly = xs[1] + ow / 2, 19.75 + 3.55 / 2, 0.36  # preprocessing -> training, routed under the lane
    ax.plot([fx, fx, tx], [oy, ly, ly], color=MUTED, lw=1.6, zorder=2)
    arrow(ax, (tx, ly), (tx, oy), color=MUTED)
    ax.text(12.5, ly, "feature table", ha="center", va="center", fontsize=8.4, color=MUTED, style="italic",
            bbox=dict(fc=GREY_BG, ec="none", pad=1.5), zorder=5)
    arrow(ax, (xs[4] + ow / 2, oy + oh), (8.4, by), color=GREEN, label="indexes", lxy=(12.0, 2.85))
    arrow(ax, (19.75 + 1.4, oy + oh), (14.6, by), color=GREEN, label="models", lxy=(17.75, 2.85))

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "Architecture_Diagram.png", dpi=150, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / "Architecture_Diagram.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / "Architecture_Diagram.pdf")


if __name__ == "__main__":
    main()
