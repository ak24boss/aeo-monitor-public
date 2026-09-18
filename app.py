"""
AEO Monitor UI — locally hosted Streamlit dashboard.
Run: streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import date

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

ROOT = Path(__file__).parent
DB_PATH = ROOT / "aeo_monitor.db"
QUERIES_PATH = ROOT / "config" / "queries.yaml"
COMPANY_PATH = ROOT / "company.yaml"


def _load_company_config() -> dict:
    if COMPANY_PATH.exists():
        with open(COMPANY_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


_company = _load_company_config()
COMPANY_NAME: str = _company.get("company_name", "Your Company")
BRAND_DOMAIN: str = _company.get("company_domain", "yourcompany.com")
BRAND_SLUG: str = BRAND_DOMAIN.split(".")[0]
COMPETITORS: list[str] = [d.split(".")[0] for d in _company.get("competitors", [])]

DOMAIN_COLORS = {
    "review_platform": "#6366f1",
    "listicle": "#f59e0b",
    "competitor_owned": "#ef4444",
    "reddit_forum": "#ff6314",
    "vendor_neutral_media": "#10b981",
    "brand_owned": "#3b82f6",
    "other": "#6b7280",
}

MECHANISM = {
    "review_platform": "Submit a listing and request a review campaign",
    "reddit_forum": "Participate in thread or craft a targeted answer",
    "listicle": "Pitch author for inclusion / publish a competing comparison",
    "competitor_owned": f"Publish a direct comparison page on {BRAND_DOMAIN}",
    "vendor_neutral_media": "Pitch journalist or author for coverage",
    "other": "Contact publisher for inclusion",
}


@st.cache_resource
def get_conn():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=60)
def load_run_dates():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT run_date FROM citation_graph ORDER BY run_date DESC"
    ).fetchall()
    return [r[0] for r in rows]


@st.cache_data(ttl=60)
def load_citation_graph(run_date):
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM citation_graph WHERE run_date = ? ORDER BY weighted_score DESC",
        [run_date],
    ).df()


@st.cache_data(ttl=60)
def load_placement_targets(run_date):
    conn = get_conn()
    return conn.execute(
        """
        SELECT
            cg.url, cg.domain, cg.domain_type, cg.weighted_score,
            cg.queries_appearing_in, cg.top_position,
            sa.brand_mentioned, sa.competitors_mentioned,
            sa.page_type, sa.last_updated, sa.pain_language
        FROM citation_graph cg
        LEFT JOIN source_analysis sa
            ON cg.url = sa.url AND sa.run_date = cg.run_date
        WHERE cg.run_date = ?
          AND cg.domain_type != 'brand_owned'
          AND (sa.brand_mentioned IS NULL OR sa.brand_mentioned = FALSE)
        ORDER BY cg.weighted_score DESC
        """,
        [run_date],
    ).df()


@st.cache_data(ttl=60)
def load_serp_results(run_date):
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM serp_results WHERE run_date = ? ORDER BY query, position",
        [run_date],
    ).df()


@st.cache_data(ttl=60)
def load_ae_citations(run_date):
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM ae_citations WHERE run_date = ?",
        [run_date],
    ).df()


@st.cache_data(ttl=60)
def load_source_analysis(run_date):
    conn = get_conn()
    return conn.execute(
        "SELECT * FROM source_analysis WHERE run_date = ?",
        [run_date],
    ).df()


@st.cache_data(ttl=300)
def load_all_queries():
    with open(QUERIES_PATH) as f:
        data = yaml.safe_load(f)
    rows = []
    for cat, items in data.get("categories", {}).items():
        for q in (items or []):
            rows.append({
                "category": cat,
                "category_label": cat.replace("_", " ").title(),
                "text": q["text"],
                "intent": q.get("intent", ""),
                "vertical": q.get("vertical", "general"),
                "priority": q.get("priority", "medium"),
            })
    return pd.DataFrame(rows)


def _parse_competitors(raw) -> list[str]:
    if not raw or (isinstance(raw, float)):
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(c) for c in parsed if c and str(c) not in ("nan", "None", "")]
        except Exception:
            return [raw] if raw not in ("nan", "None") else []
    return []


def domain_badge(dtype: str) -> str:
    color = DOMAIN_COLORS.get(dtype, "#6b7280")
    label = dtype.replace("_", " ").title()
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.75rem;">{label}</span>'


# ──────────────────────────────────────────────────────────────────────────────
# Page: Overview
# ──────────────────────────────────────────────────────────────────────────────

def page_overview(run_date):
    st.title("AEO Monitor")
    st.caption(f"Run date: **{run_date}** — {COMPANY_NAME} query visibility")

    cg = load_citation_graph(run_date)
    serp = load_serp_results(run_date)
    ae = load_ae_citations(run_date)
    targets = load_placement_targets(run_date)
    all_q = load_all_queries()

    brand_serp = serp[serp["domain"].str.contains(BRAND_SLUG, case=False, na=False)]
    queries_with_brand = brand_serp["query"].nunique()
    total_queries = serp["query"].nunique()

    brand_ae = ae[ae["cited_domain"].str.contains(BRAND_SLUG, case=False, na=False)]
    ae_queries = ae["query"].nunique()
    ae_with_brand = brand_ae["query"].nunique()

    top_opp_score = targets["weighted_score"].max() if not targets.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Queries tracked", total_queries, help="SERP queries run in this date's pipeline")
    c2.metric("SERP presence", f"{queries_with_brand}/{total_queries}", f"{queries_with_brand/total_queries*100:.0f}%" if total_queries else "0%")
    c3.metric("AE citation share", f"{ae_with_brand}/{ae_queries}", help=f"Queries where {COMPANY_NAME} appeared in Perplexity citations")
    c4.metric("Placement targets", len(targets), help=f"High-value pages where {COMPANY_NAME} is absent")
    c5.metric("Top opp score", f"{top_opp_score:.2f}", help="Highest citation weight among targets")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Citation graph — domain type mix")
        type_counts = cg.groupby("domain_type").agg(
            count=("url", "count"),
            total_score=("weighted_score", "sum"),
        ).reset_index()
        fig = px.bar(
            type_counts.sort_values("total_score", ascending=True),
            x="total_score", y="domain_type", orientation="h",
            color="domain_type",
            color_discrete_map=DOMAIN_COLORS,
            labels={"total_score": "Total citation weight", "domain_type": ""},
            height=300,
        )
        fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("AE citation share — top domains")
        if ae.empty:
            st.info("No AE citation data for this run.")
        else:
            domain_counts = ae.groupby("cited_domain").size().reset_index(name="citations")
            domain_counts = domain_counts.sort_values("citations", ascending=False).head(12)
            domain_counts["is_brand"] = domain_counts["cited_domain"].str.contains(BRAND_SLUG, case=False)
            colors = ["#3b82f6" if x else "#e2e8f0" for x in domain_counts["is_brand"]]
            fig2 = go.Figure(go.Bar(
                x=domain_counts["citations"],
                y=domain_counts["cited_domain"],
                orientation="h",
                marker_color=colors,
            ))
            fig2.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Citation count",
                yaxis_title="",
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    st.subheader("Top 10 placement targets")
    st.caption(f"High-value pages where {COMPANY_NAME} is absent, ranked by citation weight")
    for _, row in targets.head(10).iterrows():
        competitors = _parse_competitors(row.get("competitors_mentioned"))
        comp_str = ", ".join(competitors[:4]) if competitors else "none detected"
        badge = domain_badge(row["domain_type"])
        with st.container():
            cols = st.columns([4, 1, 1, 1])
            cols[0].markdown(f"**[{row['url'][:70]}...]({row['url']})**", unsafe_allow_html=False)
            cols[1].markdown(badge, unsafe_allow_html=True)
            cols[2].metric("Score", f"{row['weighted_score']:.2f}", label_visibility="collapsed")
            cols[3].metric("Queries", row["queries_appearing_in"], label_visibility="collapsed")
            if competitors:
                st.caption(f"Competitors: {comp_str}")
            st.divider()

    st.subheader("Query universe coverage")
    st.caption(f"{len(all_q)} total queries across {all_q['category'].nunique()} categories")
    cat_counts = all_q.groupby(["category", "category_label"]).size().reset_index(name="queries")
    fig3 = px.bar(
        cat_counts.sort_values("queries", ascending=True),
        x="queries", y="category_label", orientation="h",
        color_discrete_sequence=["#6366f1"],
        labels={"queries": "Queries", "category_label": ""},
        height=max(300, len(cat_counts) * 25),
    )
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig3, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# Page: Placement Targets
# ──────────────────────────────────────────────────────────────────────────────

def page_placement_targets(run_date):
    st.title("Placement Targets")
    st.caption(f"Pages where {COMPANY_NAME} is absent, ranked by citation weight. These are the highest-leverage placement opportunities.")

    targets = load_placement_targets(run_date)

    col1, col2, col3 = st.columns(3)
    domain_types = ["All"] + sorted(targets["domain_type"].unique().tolist())
    selected_type = col1.selectbox("Domain type", domain_types)
    min_score = col2.slider("Min citation score", 0.0, float(targets["weighted_score"].max()), 0.0, 0.05)
    min_queries = col3.slider("Min queries", 1, int(targets["queries_appearing_in"].max()), 1)

    df = targets.copy()
    if selected_type != "All":
        df = df[df["domain_type"] == selected_type]
    df = df[df["weighted_score"] >= min_score]
    df = df[df["queries_appearing_in"] >= min_queries]

    st.markdown(f"**{len(df)} targets** matching filters")

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        competitors = _parse_competitors(row.get("competitors_mentioned"))
        comp_str = ", ".join(competitors) if competitors else "none detected"
        badge = domain_badge(row["domain_type"])
        action = MECHANISM.get(row["domain_type"], MECHANISM["other"])

        with st.expander(f"#{rank}  {row['url'][:80]}  — score {row['weighted_score']:.2f}"):
            c1, c2, c3 = st.columns(3)
            c1.markdown(badge, unsafe_allow_html=True)
            c2.metric("Citation weight", f"{row['weighted_score']:.2f}")
            c3.metric("Appears in N queries", row["queries_appearing_in"])

            st.markdown(f"**URL:** [{row['url']}]({row['url']})")
            st.markdown(f"**Best position:** #{row['top_position']}")
            st.markdown(f"**Competitors mentioned:** {comp_str}")
            st.markdown(f"**Page type:** {row.get('page_type') or 'unknown'}")
            if row.get("last_updated") and str(row.get("last_updated")) not in ("nan", "None", ""):
                st.markdown(f"**Last updated:** {row['last_updated']}")
            st.info(f"**Action:** {action}")


# ──────────────────────────────────────────────────────────────────────────────
# Page: Query Universe
# ──────────────────────────────────────────────────────────────────────────────

def page_query_universe(run_date):
    st.title("Query Universe")
    st.caption(f"All queries in the monitoring universe. {COMPANY_NAME} presence shown for queries that have been run.")

    all_q = load_all_queries()
    serp = load_serp_results(run_date)
    ae = load_ae_citations(run_date)

    brand_serp_queries = set(
        serp[serp["domain"].str.contains(BRAND_SLUG, case=False, na=False)]["query"].unique()
    )
    brand_ae_queries = set(
        ae[ae["cited_domain"].str.contains(BRAND_SLUG, case=False, na=False)]["query"].unique()
    )
    run_queries = set(serp["query"].unique())

    all_q["run"] = all_q["text"].isin(run_queries)
    all_q["brand_in_serp"] = all_q["text"].isin(brand_serp_queries)
    all_q["brand_in_ae"] = all_q["text"].isin(brand_ae_queries)
    brand_best = (
        serp[serp["domain"].str.contains(BRAND_SLUG, case=False, na=False)]
        .groupby("query")["position"].min()
    )
    all_q["best_serp_pos"] = all_q["text"].map(brand_best)

    col1, col2, col3 = st.columns(3)
    verticals = ["All"] + sorted(all_q["vertical"].unique().tolist())
    selected_v = col1.selectbox("Vertical", verticals)
    priorities = ["All", "high", "medium", "low"]
    selected_p = col2.selectbox("Priority", priorities)
    show_unrun = col3.checkbox("Only unrun queries", value=False)

    df = all_q.copy()
    if selected_v != "All":
        df = df[df["vertical"] == selected_v]
    if selected_p != "All":
        df = df[df["priority"] == selected_p]
    if show_unrun:
        df = df[~df["run"]]

    total = len(df)
    run_count = df["run"].sum()
    brand_count = df["brand_in_serp"].sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Queries", total)
    m2.metric("Run", f"{int(run_count)}/{total}")
    m3.metric(f"{COMPANY_NAME} present (SERP)", f"{int(brand_count)}/{int(run_count)}" if run_count else "0/0")

    st.divider()

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat]
        if cat_df.empty:
            continue
        label = cat.replace("_", " ").title()
        st.subheader(label)
        for _, row in cat_df.iterrows():
            cols = st.columns([5, 1, 1, 1, 1])
            cols[0].write(row["text"])
            p_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(row["priority"], "⚪")
            cols[1].write(p_color + " " + row["priority"])
            if not row["run"]:
                cols[2].write("⬜ unrun")
            elif row["brand_in_serp"]:
                pos = int(row["best_serp_pos"]) if not pd.isna(row.get("best_serp_pos", float("nan"))) else "?"
                cols[2].write(f"✅ #{pos}")
            else:
                cols[2].write("❌ absent")
            if row["text"] in run_queries:
                cols[3].write("✅ AE" if row["brand_in_ae"] else "❌ AE")
            else:
                cols[3].write("—")
            cols[4].write(row["vertical"])
        st.divider()


# ──────────────────────────────────────────────────────────────────────────────
# Page: AE Citations
# ──────────────────────────────────────────────────────────────────────────────

def page_ae_citations(run_date):
    st.title("Answer Engine Citations")
    st.caption("Perplexity (sonar via OpenRouter) citation data — which domains get cited when buyers ask questions in your category.")

    ae = load_ae_citations(run_date)

    if ae.empty:
        st.warning("No AE citation data for this run. Run with PERPLEXITY_API_KEY set.")
        return

    total_citations = len(ae)
    unique_domains = ae["cited_domain"].nunique()
    brand_citations = ae[ae["cited_domain"].str.contains(BRAND_SLUG, case=False, na=False)]
    brand_cite_count = len(brand_citations)
    brand_share = brand_cite_count / total_citations * 100 if total_citations else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total citations", total_citations)
    c2.metric("Unique cited domains", unique_domains)
    c3.metric(f"{COMPANY_NAME} citations", brand_cite_count)
    c4.metric(f"{COMPANY_NAME} share", f"{brand_share:.1f}%")

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top cited domains")
        domain_df = ae.groupby("cited_domain").agg(
            citations=("cited_url", "count"),
            avg_position=("position_in_response", "mean"),
            queries=("query", "nunique"),
        ).reset_index().sort_values("citations", ascending=False).head(20)
        domain_df["is_brand"] = domain_df["cited_domain"].str.contains(BRAND_SLUG, case=False)
        domain_df["avg_position"] = domain_df["avg_position"].round(1)

        colors = ["#3b82f6" if x else "#94a3b8" for x in domain_df["is_brand"]]
        fig = go.Figure(go.Bar(
            x=domain_df["citations"],
            y=domain_df["cited_domain"],
            orientation="h",
            marker_color=colors,
            text=domain_df["citations"],
            textposition="outside",
        ))
        fig.update_layout(
            height=500, margin=dict(l=0, r=40, t=10, b=0),
            xaxis_title="Times cited",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Citations by query")
        query_df = ae.groupby("query").agg(
            total_citations=("cited_url", "count"),
            brand_cited=("cited_domain", lambda x: x.str.contains(BRAND_SLUG, case=False, na=False).any()),
            brand_position=("position_in_response", lambda x: (
                ae.loc[x.index][
                    ae.loc[x.index, "cited_domain"].str.contains(BRAND_SLUG, case=False, na=False)
                ]["position_in_response"].min()
                if ae.loc[x.index, "cited_domain"].str.contains(BRAND_SLUG, case=False, na=False).any()
                else None
            )),
        ).reset_index().sort_values("brand_cited", ascending=False)

        for _, row in query_df.iterrows():
            icon = "✅" if row["brand_cited"] else "❌"
            lp = row.get("brand_position")
            pos_str = f" (pos #{int(lp)})" if row["brand_cited"] and pd.notna(lp) else ""
            st.markdown(f"{icon} **{row['query']}**{pos_str} — {int(row['total_citations'])} citations")

    st.divider()

    st.subheader(f"Citation position distribution — {COMPANY_NAME}")
    if brand_cite_count:
        pos_counts = brand_citations["position_in_response"].value_counts().reset_index()
        pos_counts.columns = ["position", "count"]
        pos_counts = pos_counts.sort_values("position")
        fig2 = px.bar(pos_counts, x="position", y="count",
                      color_discrete_sequence=["#3b82f6"],
                      labels={"position": "Position in citation list", "count": "Frequency"},
                      title=f"Where {COMPANY_NAME} appears in Perplexity citation lists")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info(f"{COMPANY_NAME} was not cited in any AE response for this run.")

    st.subheader("Competitor citation presence")
    comp_rows = []
    for comp in COMPETITORS:
        mask = ae["cited_domain"].str.contains(comp, case=False, na=False)
        if mask.any():
            comp_rows.append({
                "competitor": comp,
                "citations": int(mask.sum()),
                "queries": int(ae[mask]["query"].nunique()),
                "avg_position": round(ae[mask]["position_in_response"].mean(), 1),
            })
    if comp_rows:
        comp_df = pd.DataFrame(comp_rows).sort_values("citations", ascending=False)
        comp_df[COMPANY_NAME] = brand_cite_count
        st.dataframe(comp_df, use_container_width=True, hide_index=True)
    elif COMPETITORS:
        st.info("No competitor citations found in this run.")
    else:
        st.info("Add competitors to company.yaml to see competitor citation data here.")


# ──────────────────────────────────────────────────────────────────────────────
# Page: SERP Analysis
# ──────────────────────────────────────────────────────────────────────────────

def page_serp(run_date):
    st.title("SERP Analysis")
    st.caption(f"Organic search results for tracked queries. Shows which pages dominate each query and where {COMPANY_NAME} appears.")

    serp = load_serp_results(run_date)
    cg = load_citation_graph(run_date)

    queries = sorted(serp["query"].unique())
    selected_q = st.selectbox("Select query", queries)

    q_df = serp[serp["query"] == selected_q].sort_values("position")

    brand_rows = q_df[q_df["domain"].str.contains(BRAND_SLUG, case=False, na=False)]
    if not brand_rows.empty:
        best_pos = brand_rows["position"].min()
        st.success(f"{COMPANY_NAME} appears at position #{best_pos} for this query")
    else:
        st.warning(f"{COMPANY_NAME} is absent from SERP results for this query")

    for _, row in q_df.iterrows():
        is_brand = BRAND_SLUG in str(row["domain"]).lower()
        border = "border-left: 4px solid #3b82f6; padding-left: 10px;" if is_brand else ""
        cg_row = cg[cg["url"] == row["url"]]
        score_str = f" — citation score: {cg_row['weighted_score'].values[0]:.2f}" if not cg_row.empty else ""

        with st.container():
            st.markdown(
                f'<div style="{border}">'
                f'<b>#{row["position"]}</b> <a href="{row["url"]}">{row["url"][:80]}</a> '
                f'<span style="color:#6b7280;font-size:0.8rem;">{row["domain"]}</span> '
                f'<span style="color:#6b7280;font-size:0.8rem;">{score_str}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if row.get("snippet"):
                st.caption(str(row["snippet"])[:200])

    st.divider()
    st.subheader("Query presence matrix")
    st.caption(f"Which queries does {COMPANY_NAME} appear in? Green = present, Red = absent")

    brand_by_q = (
        serp.groupby("query")
        .apply(lambda d: d["domain"].str.contains(BRAND_SLUG, case=False, na=False).any())
        .reset_index()
    )
    brand_by_q.columns = ["query", "brand_present"]
    brand_by_q["best_position"] = brand_by_q["query"].map(
        serp[serp["domain"].str.contains(BRAND_SLUG, case=False, na=False)]
        .groupby("query")["position"].min()
    )
    brand_by_q = brand_by_q.sort_values(["brand_present", "best_position"], ascending=[False, True])

    for _, row in brand_by_q.iterrows():
        icon = "✅" if row["brand_present"] else "❌"
        pos_str = f" — pos #{int(row['best_position'])}" if row["brand_present"] and not pd.isna(row.get("best_position")) else ""
        st.write(f"{icon} {row['query']}{pos_str}")


# ──────────────────────────────────────────────────────────────────────────────
# Page: Weekly Diff
# ──────────────────────────────────────────────────────────────────────────────

def page_weekly_diff():
    st.title("Weekly Diff")
    st.caption("Changes in citation graph between runs.")

    run_dates = load_run_dates()
    if len(run_dates) < 2:
        st.info("Only one run in the database. Run the pipeline again next week to see diffs.")
        if run_dates:
            st.write(f"Current run date: {run_dates[0]}")
        diff_path = ROOT / "out" / "weekly_diff.md"
        if diff_path.exists():
            st.markdown(diff_path.read_text())
        return

    col1, col2 = st.columns(2)
    current_date = col1.selectbox("Current run", run_dates, index=0)
    prev_options = [d for d in run_dates if d < current_date]
    if not prev_options:
        st.warning("No earlier run available.")
        return
    prev_date = col2.selectbox("Compare with", prev_options, index=0)

    conn = get_conn()
    current = conn.execute(
        "SELECT url, weighted_score, domain_type FROM citation_graph WHERE run_date = ?",
        [current_date],
    ).df().set_index("url")
    previous = conn.execute(
        "SELECT url, weighted_score, domain_type FROM citation_graph WHERE run_date = ?",
        [prev_date],
    ).df().set_index("url")

    new_urls = set(current.index) - set(previous.index)
    dropped_urls = set(previous.index) - set(current.index)
    common = set(current.index) & set(previous.index)
    changed = {
        url: current.loc[url, "weighted_score"] - previous.loc[url, "weighted_score"]
        for url in common
        if abs(current.loc[url, "weighted_score"] - previous.loc[url, "weighted_score"]) > 0.01
    }

    c1, c2, c3 = st.columns(3)
    c1.metric("New entries", len(new_urls))
    c2.metric("Dropped", len(dropped_urls))
    c3.metric("Score changes", len(changed))

    if new_urls:
        st.subheader("New URLs")
        for url in sorted(new_urls, key=lambda u: -current.loc[u, "weighted_score"])[:15]:
            score = current.loc[url, "weighted_score"]
            dtype = current.loc[url, "domain_type"]
            st.write(f"+ [{url[:70]}]({url}) ({dtype}, score={score:.2f})")

    if dropped_urls:
        st.subheader("Dropped URLs")
        for url in sorted(dropped_urls, key=lambda u: -previous.loc[u, "weighted_score"])[:15]:
            score = previous.loc[url, "weighted_score"]
            st.write(f"- [{url[:70]}]({url}) (was {score:.2f})")

    if changed:
        st.subheader("Score changes")
        sorted_changed = sorted(changed.items(), key=lambda x: abs(x[1]), reverse=True)[:15]
        for url, delta in sorted_changed:
            sign = "+" if delta > 0 else ""
            color = "green" if delta > 0 else "red"
            st.markdown(
                f'<span style="color:{color};">{sign}{delta:.2f}</span> [{url[:70]}]({url})',
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title=f"AEO Monitor — {COMPANY_NAME}",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.4rem; }
    .stExpander { border: 1px solid #e2e8f0; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)

    run_dates = load_run_dates()
    if not run_dates:
        st.error("No data in database. Run: python __main__.py run")
        return

    with st.sidebar:
        st.markdown("## 📡 AEO Monitor")
        st.caption(f"{COMPANY_NAME} citation & visibility tracker")
        st.divider()

        run_date = st.selectbox(
            "Run date",
            run_dates,
            format_func=lambda d: str(d),
        )

        page = st.radio(
            "View",
            ["Overview", "Placement Targets", "Query Universe", "AE Citations", "SERP Analysis", "Weekly Diff"],
            label_visibility="collapsed",
        )

        st.divider()
        st.caption(f"DB: {DB_PATH.name}")
        conn = get_conn()
        cg_count = conn.execute(
            "SELECT COUNT(*) FROM citation_graph WHERE run_date = ?", [run_date]
        ).fetchone()[0]
        st.caption(f"{cg_count} URLs in citation graph")

    if page == "Overview":
        page_overview(run_date)
    elif page == "Placement Targets":
        page_placement_targets(run_date)
    elif page == "Query Universe":
        page_query_universe(run_date)
    elif page == "AE Citations":
        page_ae_citations(run_date)
    elif page == "SERP Analysis":
        page_serp(run_date)
    elif page == "Weekly Diff":
        page_weekly_diff()


if __name__ == "__main__":
    main()
