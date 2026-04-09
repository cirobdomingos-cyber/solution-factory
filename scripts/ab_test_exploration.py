"""Quick A/B test for exploration modes on the same domain."""

from __future__ import annotations

from collections import Counter

from agents.topic_explorer import TopicExplorerAgent
from agents.trend_explorer import OnlineTrendExplorerAgent


DOMAIN = "health and wellbeing"


def run() -> None:
    ctx = {"user_prompt": DOMAIN}

    brainstorm = TopicExplorerAgent().run(dict(ctx))
    online = OnlineTrendExplorerAgent().run(dict(ctx))

    angles = brainstorm.get("exploration_angles", []) or []
    paths = online.get("exploration_paths", []) or []

    cat_counts = Counter([a.get("category", "other") for a in angles])
    broad_counts = Counter([p.get("broad_area", "Other") for p in paths])
    momentum_counts = Counter([p.get("momentum", "unknown") for p in paths])

    print("=== Exploration Mode A/B Test ===")
    print(f"Domain: {DOMAIN}")
    print()

    print("[Brainstorm Mode]")
    print(f"Angles: {len(angles)}")
    print(f"Category coverage: {len(cat_counts)} categories")
    print("Top categories:", dict(cat_counts.most_common(6)))
    for i, a in enumerate(angles[:3], 1):
        print(
            f"{i}. {a.get('title', '?')} | {a.get('category', '?')} | "
            f"heat={a.get('heat_level', '?')}"
        )

    print()
    print("[Online Trends Mode]")
    print(f"Paths: {len(paths)}")
    print(f"Broad-area coverage: {len(broad_counts)}")
    print("Top broad areas:", dict(broad_counts.most_common(6)))
    print("Momentum mix:", dict(momentum_counts))
    for i, p in enumerate(paths[:3], 1):
        print(
            f"{i}. {p.get('broad_area', '?')} -> {p.get('mid_area', '?')} -> "
            f"{p.get('narrow_area', '?')} | momentum={p.get('momentum', '?')}"
        )

    brainstorm_non_obvious = sum(
        1 for a in angles if "contrarian" in (a.get("description", "").lower())
    )
    online_with_signals = sum(
        1 for p in paths if len(p.get("source_signals", []) or []) >= 2
    )
    online_with_queries = sum(
        1 for p in paths if len(p.get("starter_queries", []) or []) >= 2
    )

    print()
    print("[Quality Signals]")
    print(f"Brainstorm explicit contrarian mentions: {brainstorm_non_obvious}")
    print(
        "Online paths with >=2 source signals: "
        f"{online_with_signals}/{len(paths) if paths else 0}"
    )
    print(
        "Online paths with >=2 starter queries: "
        f"{online_with_queries}/{len(paths) if paths else 0}"
    )

    print()
    print("[Verdict]")
    if paths and online_with_signals >= max(3, len(paths) // 2):
        print(
            "Online Trends mode produced stronger evidence-backed narrowing "
            "for execution decisions."
        )
    else:
        print(
            "Brainstorm mode is faster and still useful for ideation; "
            "online mode may need rerun for richer evidence."
        )


if __name__ == "__main__":
    run()
