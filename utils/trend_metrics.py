"""Trend metrics display and analysis utilities.

Provides functions to render trend data with auto-categorized metrics, momentum
indicators, and real-time signals in a dashboard format.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import streamlit as st


def _categorize_trend(title: str, description: str, source_signals: list[str]) -> str:
    """Auto-categorize a trend based on title, description, and signals.
    
    Returns a category slug (e.g. 'technology', 'regulation', 'market_shift').
    
    This is a lightweight heuristic — in production, you might use LLM-based
    classification or a predefined taxonomy. For now, match keywords.
    """
    combined = f"{title} {description} {' '.join(source_signals)}".lower()
    
    category_keywords = {
        "technology": ["ai", "llm", "automation", "software", "tool", "platform", "algorithm", "api"],
        "regulation": ["law", "regulation", "policy", "compliance", "gdpr", "sec", "legislation"],
        "market_shift": ["shift", "trend", "market", "consumer", "demand", "adoption", "growth"],
        "funding": ["funding", "venture", "acquisition", "acquisition", "series", "round", "investment"],
        "competitive": ["competitor", "launch", "competitor", "entrant", "market entry"],
        "labor": ["hiring", "talent", "workforce", "labor", "skill"],
        "consumer": ["user", "customer", "consumer", "pain", "frustration", "complaint"],
    }
    
    scores = {}
    for category, keywords in category_keywords.items():
        score = sum(combined.count(kw) for kw in keywords)
        if score > 0:
            scores[category] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "market_shift"


def render_exploration_metrics(exploration_output: dict) -> None:
    """Render metrics dashboard for OnlineTrendExplorerAgent output.
    
    Shows:
    - Broad area breakdown with path count per area
    - Momentum distribution (hot/warm/cool)
    - Average signal richness per path
    - Interactive trend explorer
    
    Args:
        exploration_output: Dict with keys:
            - exploration_domain (str)
            - broad_areas (list of dicts with title, signal_summary)
            - exploration_paths (list of dicts with broad_area, momentum, source_signals, etc.)
    """
    if not exploration_output or not exploration_output.get("exploration_paths"):
        st.warning("No exploration data available.")
        return
    
    paths = exploration_output.get("exploration_paths", [])
    broad_areas = exploration_output.get("broad_areas", [])
    domain = exploration_output.get("exploration_domain", "Unknown Domain")
    
    # Calculate metrics
    broad_area_counts = Counter(p.get("broad_area", "Other") for p in paths)
    momentum_counts = Counter(p.get("momentum", "warm") for p in paths)
    avg_signals = sum(len(p.get("source_signals", [])) for p in paths) / len(paths) if paths else 0
    
    # Layout: 4 metrics
    st.markdown("### 📊 Exploration Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Paths", len(paths))
    with col2:
        st.metric("Broad Areas", len(broad_area_counts))
    with col3:
        hot_count = momentum_counts.get("hot", 0)
        st.metric("🔥 Hot Opportunities", hot_count, delta=f"{hot_count}/{len(paths)}")
    with col4:
        st.metric("Avg Signals/Path", f"{avg_signals:.1f}")
    
    st.divider()
    
    # Broad area breakdown
    st.markdown("### 🌐 Coverage by Broad Area")
    area_data = []
    for area in sorted(broad_area_counts.keys()):
        count = broad_area_counts[area]
        momentum_dist = Counter(
            p.get("momentum", "warm") for p in paths if p.get("broad_area") == area
        )
        hot = momentum_dist.get("hot", 0)
        warm = momentum_dist.get("warm", 0)
        cool = momentum_dist.get("cool", 0)
        
        area_data.append({
            "Broad Area": area,
            "Paths": count,
            "🔥 Hot": hot,
            "🟠 Warm": warm,
            "❄️ Cool": cool,
        })
    
    if area_data:
        st.dataframe(area_data, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # Momentum summary
    st.markdown("### 🎯 Opportunity Momentum Summary")
    col1, col2, col3 = st.columns(3)
    
    hot = momentum_counts.get("hot", 0)
    warm = momentum_counts.get("warm", 0)
    cool = momentum_counts.get("cool", 0)
    
    with col1:
        st.success(f"**🔥 Hot:** {hot} paths")
        st.caption("High market activity, clear signals")
    with col2:
        st.info(f"**🟠 Warm:** {warm} paths")
        st.caption("Emerging, mixed signals")
    with col3:
        st.warning(f"**❄️ Cool:** {cool} paths")
        st.caption("Early or niche, fewer signals")
    
    st.divider()
    
    # Signal richness breakdown
    st.markdown("### 🔍 Signal Richness by Path")
    signal_data = []
    for idx, path in enumerate(paths):
        broad = path.get("broad_area", "Other")
        mid = path.get("mid_area", "?")
        narrow = path.get("narrow_area", "?")
        momentum = path.get("momentum", "warm")
        signals = path.get("source_signals", [])
        
        signal_data.append({
            "Broad Area": broad,
            "Narrow Focus": narrow,
            "Momentum": momentum.upper(),
            "Signal Count": len(signals),
            "Queries": len(path.get("starter_queries", [])),
        })
    
    if signal_data:
        st.dataframe(signal_data, use_container_width=True, hide_index=True, column_config={
            "Signal Count": st.column_config.NumberColumn("Signal Count", format="%d"),
            "Queries": st.column_config.NumberColumn("Queries", format="%d"),
        })


def render_trend_metrics(trends_output: dict) -> None:
    """Render metrics dashboard for TrendResearchAgent output (Phase 0).
    
    Shows:
    - Market sentiment and key takeaway
    - Trend count by auto-detected category
    - Recency distribution
    - Interactive trend explorer table
    
    Args:
        trends_output: Dict with keys:
            - trends (list of dicts: title, description, source_signals, recency, opportunity_implication)
            - market_sentiment (str: "bullish", "cautious", "bearish")
            - key_takeaway (str)
            - domain (str, optional)
            - search_queries_used (list, optional)
    """
    if not trends_output or not trends_output.get("trends"):
        st.warning("No trend data available.")
        return
    
    trends = trends_output.get("trends", [])
    sentiment = trends_output.get("market_sentiment", "cautious")
    takeaway = trends_output.get("key_takeaway", "")
    domain = trends_output.get("domain", "Unknown Domain")
    
    # Metrics calculations
    categories = Counter(_categorize_trend(
        t.get("title", ""), t.get("description", ""), t.get("source_signals", [])
    ) for t in trends)
    
    recency_counts = Counter(t.get("recency", "unknown") for t in trends)
    total_signals = sum(len(t.get("source_signals", [])) for t in trends)
    
    # Sentiment color mapping
    sentiment_color_map = {"bullish": "green", "cautious": "orange", "bearish": "red"}
    sentiment_color = sentiment_color_map.get(sentiment, "blue")
    
    # Layout: Key metrics
    st.markdown("### 📈 Phase 0: Market Trend Intelligence")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Trends Found", len(trends))
    with col2:
        st.markdown(f"**Sentiment:** :{sentiment_color}[{sentiment.upper()}]")
    with col3:
        st.metric("Data Points", total_signals)
    with col4:
        queries = trends_output.get("search_queries_used", [])
        st.metric("Search Queries", len(queries))
    
    if takeaway:
        st.divider()
        st.info(f"**🎯 Key Takeaway:** {takeaway}")
    
    st.divider()
    
    # Category breakdown
    st.markdown("### 🏷️ Trends by Category")
    cat_cols = len(categories)
    if cat_cols > 0:
        cat_cols_list = st.columns(cat_cols)
        for (category, count), col in zip(sorted(categories.items(), key=lambda x: -x[1]), cat_cols_list):
            with col:
                st.metric(category.title(), count)
    
    st.divider()
    
    # Recency distribution
    st.markdown("### ⏱️ Recency of Signals")
    recency_order = ["last_week", "last_month", "last_quarter", "last_year"]
    recency_display = []
    for r in recency_order:
        if r in recency_counts:
            recency_display.append({"Timeframe": r.replace("_", " ").title(), "Count": recency_counts[r]})
    
    if recency_display:
        st.dataframe(recency_display, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # Trends explorer table
    st.markdown("### 🔍 Detailed Trend Breakdown")
    trend_data = []
    for trend in trends:
        title = trend.get("title", "?")
        category = _categorize_trend(
            title,
            trend.get("description", ""),
            trend.get("source_signals", [])
        )
        recency = trend.get("recency", "unknown").replace("_", " ").title()
        signal_count = len(trend.get("source_signals", []))
        
        trend_data.append({
            "Trend": title,
            "Category": category.title(),
            "Recency": recency,
            "Signals": signal_count,
        })
    
    if trend_data:
        st.dataframe(trend_data, use_container_width=True, hide_index=True, column_config={
            "Signals": st.column_config.NumberColumn("Signals", format="%d"),
        })
    
    # Expandable detail view
    st.divider()
    st.markdown("### 📋 Full Trend Details")
    for idx, trend in enumerate(trends):
        title = trend.get("title", "Untitled")
        recency = trend.get("recency", "?")
        description = trend.get("description", "")
        signals = trend.get("source_signals", [])
        implication = trend.get("opportunity_implication", "")
        
        with st.expander(f"**{title}** — _{recency}_"):
            st.markdown(description)
            if signals:
                st.markdown("**Evidence:**")
                for s in signals:
                    st.markdown(f"- {s}")
            if implication:
                st.success(f"**Builder implication:** {implication}")
