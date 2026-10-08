"""
AEO Monitor UI — locally hosted Streamlit dashboard.
Run: streamlit run dashboard.py
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

import os

ROOT = Path(__file__).parent

# Company-aware path resolution:
# - COMPANY_SLUG env var → read from companies/{slug}/
# - Otherwise → legacy root paths
_COMPANY_SLUG = os.environ.get("COMPANY_SLUG", "")
if _COMPANY_SLUG:
    _COMPANY_DIR = ROOT / "companies" / _COMPANY_SLUG
    DB_PATH = _COMPANY_DIR / "data.db"
    QUERIES_PATH = _COMPANY_DIR / "queries.yaml"
    COMPANY_PATH = _COMPANY_DIR / "profile.yaml"
else:
    _COMPANY_DIR = ROOT
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
    "review_platform": "#4B5340",    # olive-drab
    "listicle": "#E09A3F",           # harvest-amber
    "competitor_owned": "#ef4444",   # red (warning)
    "reddit_forum": "#ff6314",       # orange
    "vendor_neutral_media": "#10b981",
    "brand_owned": "#E09A3F",        # harvest-amber
    "other": "#362C24",              # bark-brown
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
    if not DB_PATH.exists():
        return None
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=60)
def load_run_dates():
    conn = get_conn()
    if conn is None:
        return []
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


@st.cache_data(ttl=60)
def load_ae_probe_results(run_date):
    conn = get_conn()
    if conn is None:
        return pd.DataFrame()
    try:
        return conn.execute(
            "SELECT * FROM ae_probe_results WHERE run_date = ? ORDER BY engine, probe_id",
            [run_date],
        ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_cross_reference(run_date):
    conn = get_conn()
    if conn is None:
        return pd.DataFrame()
    try:
        return conn.execute(
            "SELECT * FROM cross_reference WHERE run_date = ? ORDER BY serp_weighted_score DESC",
            [run_date],
        ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_sov_history():
    """Return a DataFrame with SOV % per engine per run_date across all historical runs."""
    conn = get_conn()
    if conn is None:
        return pd.DataFrame()
    try:
        return conn.execute("""
            SELECT run_date, engine,
                   AVG(CASE WHEN brand_mentioned THEN 100.0 ELSE 0.0 END) AS sov_pct,
                   COUNT(*) AS probe_count
            FROM ae_probe_results
            GROUP BY run_date, engine
            ORDER BY run_date, engine
        """).df()
    except Exception:
        return pd.DataFrame()


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
            colors = ["#E09A3F" if x else "#DFD9CE" for x in domain_counts["is_brand"]]
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
        color_discrete_sequence=["#4B5340"],
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

        colors = ["#E09A3F" if x else "#DFD9CE" for x in domain_df["is_brand"]]
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
                      color_discrete_sequence=["#E09A3F"],
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
        border = "border-left: 4px solid #E09A3F; padding-left: 10px;" if is_brand else ""
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
# Page: AI Engine Visibility
# ──────────────────────────────────────────────────────────────────────────────

# Petra Labs prompt-type ordering (most citation movement → least)
_PT_ORDER = [
    "how-to",           # Class C — highest movement
    "persona-regulated","requirements","competitor","pain",  # Class B top
    "use-case","price-budget","persona-casual","price-premium",  # Class B mid/low
    "seed",             # baseline seed
    "simplify","best","recommend","spanish","typo",  # Class A — lowest movement
]
_PT_CLASS = {
    "how-to": "C", "persona-regulated": "B", "requirements": "B",
    "competitor": "B", "pain": "B", "use-case": "B", "price-budget": "B",
    "persona-casual": "B", "price-premium": "B", "seed": "seed",
    "simplify": "A", "best": "A", "recommend": "A", "spanish": "A", "typo": "A",
}
_CLASS_COLOR = {"C": "#4B5340", "B": "#E09A3F", "seed": "#10b981", "A": "#362C24"}

_REVIEW_PLATFORMS = {"g2.com", "learn.g2.com", "capterra.com", "gartner.com", "trustpilot.com",
                     "getapp.com", "trustradius.com", "software-advice.com", "peer.gartner.com",
                     "sourceforge.net", "slashdot.org", "crozdesk.com", "ormco.com"}
_COMMUNITY_SITES = {"reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
                    "news.ycombinator.com", "dev.to", "medium.com", "substack.com"}
_TECH_MEDIA = {"techcrunch.com", "forbes.com", "venturebeat.com", "zdnet.com", "theregister.com",
               "wired.com", "thenextweb.com", "infoq.com", "techtarget.com", "computerworld.com"}


def _classify_domain(domain: str, brand_domain: str, competitor_domains: list[str]) -> str:
    d = domain.lower().rstrip("/")
    if d == brand_domain.lower().rstrip("/") or brand_domain.split(".")[0].lower() in d:
        return "brand"
    if d in _REVIEW_PLATFORMS:
        return "review platform"
    if d in _COMMUNITY_SITES:
        return "community"
    if d in _TECH_MEDIA:
        return "tech media"
    for cd in competitor_domains:
        if cd.lower().rstrip("/") in d:
            return "competitor"
    return "general web"


_DOMAIN_TYPE_COLORS = {
    "brand": "#E09A3F",
    "review platform": "#4B5340",
    "community": "#f59e0b",
    "competitor": "#ef4444",
    "tech media": "#8b5cf6",
    "general web": "#362C24",
}

_TOPIC_LABEL = {
    "doc-extraction": "Document Extraction",
    "invoice-ocr": "Invoice OCR",
    "idp": "Intelligent Doc Processing",
    "pdf-parsing": "Document Parsing API",
    "healthcare-doc": "Healthcare",
    "legal-doc": "Legal / Contracts",
    "ap-automation": "Accounts Payable",
    "insurance-claims": "Insurance Claims",
    "logistics-doc": "Logistics / Freight",
    "general": "General",
}


def _compute_visibility_score(probes_df: pd.DataFrame, engines: list[str]) -> tuple[float, dict]:
    """Composite Elmo Visibility Score 0–100.

    Three components:
    - Engine-weighted SOV (60%): Perplexity 40%, OpenAI 35%, Claude 25% — reflects actual search citation share
    - Vertical breadth (25%): % of seed topics with ≥1 brand mention
    - High-movement class coverage (15%): mention rate across Class B + C probes (Petra Labs WJD 0.80/0.97)
    """
    engine_weights = {"perplexity": 0.30, "openai": 0.30, "gemini": 0.25, "google": 0.15, "claude": 0.25}

    eng_sov = 0.0
    for eng in engines:
        e_df = probes_df[probes_df["engine"] == eng]
        if e_df.empty:
            continue
        eng_sov += engine_weights.get(eng, 0.25) * e_df["brand_mentioned"].mean() * 100

    topics = [t for t in probes_df["seed_topic"].unique() if t != "general"]
    vert_with_mention = sum(
        1 for t in topics
        if probes_df[probes_df["seed_topic"] == t]["brand_mentioned"].any()
    )
    vert_breadth = (vert_with_mention / len(topics) * 100) if topics else 0.0

    bc_df = probes_df[probes_df["perturbation_class"].isin(["B", "C"])]
    bc_coverage = bc_df["brand_mentioned"].mean() * 100 if not bc_df.empty else 0.0

    score = min(0.60 * eng_sov + 0.25 * vert_breadth + 0.15 * bc_coverage, 100.0)
    return score, {
        "Engine-weighted SOV": eng_sov,
        "Vertical breadth": vert_breadth,
        "Class B/C coverage": bc_coverage,
    }


def _extract_response_text(raw_response_str: str) -> str:
    """Extract the assistant message content from a raw OpenRouter API response JSON."""
    if not raw_response_str:
        return ""
    try:
        data = json.loads(raw_response_str)
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
    except Exception:
        pass
    return ""


def _safe_context(val) -> str:
    """Return brand context string, or empty string for None/NaN/empty."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s in ("nan", "None", "") else s


def _safe_json_list(val) -> list:
    if not val or (isinstance(val, float) and pd.isna(val)):
        return []
    try:
        return json.loads(val) if isinstance(val, str) else list(val)
    except Exception:
        return []


def _ensure_probe_cols(df: pd.DataFrame) -> pd.DataFrame:
    for col, default in [
        ("perturbation_type", "seed"),
        ("perturbation_class", "seed"),
        ("seed_topic", "general"),
    ]:
        if col not in df.columns:
            df[col] = default
    return df


def page_ai_engine_visibility(run_date):
    st.title("Elmo")
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.caption(
            f"AI engine visibility for **{COMPANY_NAME}** — "
            "60 probes × 15 Petra Labs perturbation types × 3 engines. "
            "Navigate the tabs below: Overview → Prompt Heatmap → Citation Space → Competitive → Opportunities."
        )
    with col_h2:
        st.caption(f"Run date: {run_date}")

    probes_df = load_ae_probe_results(run_date)
    xref_df = load_cross_reference(run_date)

    if probes_df.empty:
        st.warning(
            "No AI engine probe data for this run. "
            "Run: `make dev-run-lido` with `OPENROUTER_API_KEY` set."
        )
        return

    probes_df = _ensure_probe_cols(probes_df)
    engines = sorted(probes_df["engine"].unique().tolist())
    n_probes = len(probes_df)
    n_mentions = int(probes_df["brand_mentioned"].sum())
    sov_pct = n_mentions / n_probes * 100 if n_probes else 0
    n_pt_types = probes_df["perturbation_type"].nunique()
    n_pt_with_mention = probes_df[probes_df["brand_mentioned"]]["perturbation_type"].nunique()
    coverage_pct = n_pt_with_mention / n_pt_types * 100 if n_pt_types else 0
    critical_gaps = int((xref_df["action_priority"] == "critical").sum()) if not xref_df.empty else 0

    # Composite score
    vis_score, score_components = _compute_visibility_score(probes_df, engines)
    score_label = (
        "Dominant" if vis_score >= 80 else
        "Category authority" if vis_score >= 50 else
        "Niche presence" if vis_score >= 20 else
        "Emerging"
    )
    score_color = (
        "#16a34a" if vis_score >= 80 else
        "#22c55e" if vis_score >= 50 else
        "#f59e0b" if vis_score >= 20 else
        "#ef4444"
    )

    # Hero score + top-line metrics in one row
    hero_col, metrics_col = st.columns([1, 2])
    with hero_col:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=vis_score,
            domain={"x": [0, 1], "y": [0, 1]},
            number={"suffix": "/100", "font": {"size": 32, "color": score_color}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#94a3b8"},
                "bar": {"color": score_color, "thickness": 0.3},
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 20], "color": "#fef2f2"},
                    {"range": [20, 50], "color": "#fefce8"},
                    {"range": [50, 80], "color": "#f0fdf4"},
                    {"range": [80, 100], "color": "#dcfce7"},
                ],
            },
            title={"text": f"Elmo Visibility Score<br><span style='font-size:0.8em;color:{score_color}'>{score_label}</span>",
                   "font": {"size": 14}},
        ))
        fig_gauge.update_layout(height=200, margin=dict(l=20, r=20, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_gauge, use_container_width=True)

    with metrics_col:
        st.write("")
        m1, m2 = st.columns(2)
        m1.metric("Engines", len(engines))
        m2.metric("Probe runs", n_probes)
        m3, m4 = st.columns(2)
        m3.metric(f"Overall SOV", f"{sov_pct:.1f}%")
        m4.metric("Critical SERP gaps", critical_gaps)
        # Score breakdown
        st.caption("**Score components:**")
        for label, val in score_components.items():
            pct = min(val, 100)
            bar_color = "#10b981" if pct >= 40 else "#f59e0b" if pct >= 15 else "#ef4444"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                f'<span style="width:170px;font-size:0.8rem;color:#64748b;">{label}</span>'
                f'<div style="flex:1;background:#f1f5f9;border-radius:4px;height:12px;">'
                f'<div style="width:{pct}%;background:{bar_color};border-radius:4px;height:12px;"></div>'
                f'</div>'
                f'<span style="width:40px;text-align:right;font-size:0.8rem;font-weight:600;">{pct:.0f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "🔥 Prompt Heatmap",
        "🌐 Citation Space",
        "⚔️ Competitive",
        "🎯 Opportunities",
        "📢 Sponsored Ads",
    ])

    # ── Tab 1: Overview ────────────────────────────────────────────────────────
    with tab1:
        # Vertical performance summary — most useful top-of-page view
        st.subheader("Visibility by Vertical")
        vert_rows = []
        for topic in sorted(probes_df["seed_topic"].unique()):
            if topic == "general":
                continue
            t_df = probes_df[probes_df["seed_topic"] == topic]
            total = len(t_df)
            ment = int(t_df["brand_mentioned"].sum())
            # Best engine for this vertical
            best_eng = ""
            best_pct = 0.0
            for eng in engines:
                e_df = t_df[t_df["engine"] == eng]
                if e_df.empty:
                    continue
                pct = e_df["brand_mentioned"].mean() * 100
                if pct > best_pct:
                    best_pct = pct
                    best_eng = eng
            vert_rows.append({
                "Vertical": _TOPIC_LABEL.get(topic, topic),
                "Probes": total,
                "Mentions": ment,
                "SOV %": round(ment / total * 100, 1) if total else 0.0,
                "Best engine": f"{best_eng} ({best_pct:.0f}%)" if best_eng else "—",
            })
        if vert_rows:
            vdf = pd.DataFrame(vert_rows).sort_values("SOV %", ascending=False)
            vert_colors = [
                "#10b981" if r["SOV %"] >= 20 else "#f59e0b" if r["SOV %"] >= 5 else "#ef4444"
                for r in vert_rows
            ]
            fig_vert = go.Figure(go.Bar(
                x=vdf["SOV %"],
                y=vdf["Vertical"],
                orientation="h",
                marker_color=[
                    "#10b981" if v >= 20 else "#f59e0b" if v >= 5 else "#ef4444"
                    for v in vdf["SOV %"]
                ],
                text=[f'{v:.0f}%' for v in vdf["SOV %"]],
                textposition="outside",
            ))
            fig_vert.update_layout(
                height=340, xaxis_range=[0, max(vdf["SOV %"].max() * 1.3, 30)],
                xaxis_title="SOV % (all engines combined)",
                margin=dict(l=170, r=60, t=10, b=10),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_vert, use_container_width=True)
            st.dataframe(vdf, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Share of Voice by Engine")
        sov_rows = []
        for eng in engines:
            e_df = probes_df[probes_df["engine"] == eng]
            tot = len(e_df)
            ment = int(e_df["brand_mentioned"].sum())
            sov_rows.append({
                "Engine": eng.title(),
                "Probe runs": tot,
                f"{COMPANY_NAME} mentions": ment,
                "SOV %": round(ment / tot * 100, 1) if tot else 0.0,
            })
        sov_df = pd.DataFrame(sov_rows)
        st.dataframe(sov_df, use_container_width=True, hide_index=True)

        fig_sov = go.Figure()
        for eng_row in sov_df.itertuples():
            pct = eng_row._4  # SOV %
            color = "#10b981" if pct >= 50 else "#f59e0b" if pct >= 20 else "#ef4444"
            fig_sov.add_trace(go.Bar(
                name=eng_row.Engine, x=[eng_row.Engine], y=[pct],
                marker_color=color, text=[f"{pct}%"], textposition="outside",
            ))
        fig_sov.update_layout(
            height=280, showlegend=False, yaxis_range=[0, 110],
            yaxis_title="SOV %", margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig_sov, use_container_width=True)

        # ── SOV trend over time ────────────────────────────────────────────────
        st.divider()
        st.subheader("SOV Trend Over Time")
        history_df = load_sov_history()
        n_dates = history_df["run_date"].nunique() if not history_df.empty else 0
        if n_dates < 2:
            st.info(
                f"Trend line requires ≥2 weekly pipeline runs. "
                f"Currently: {n_dates} run{'s' if n_dates != 1 else ''}. "
                "Run `make run-company COMPANY=lido` weekly to populate."
            )
        else:
            engine_colors_trend = {
                "perplexity": "#8b5cf6",
                "openai": "#10b981",
                "gemini": "#E09A3F",
                "google": "#4B5340",
                "claude": "#f59e0b",  # legacy
            }
            fig_trend = go.Figure()
            for eng in history_df["engine"].unique():
                eng_h = history_df[history_df["engine"] == eng].sort_values("run_date")
                fig_trend.add_trace(go.Scatter(
                    x=eng_h["run_date"], y=eng_h["sov_pct"],
                    mode="lines+markers",
                    name=eng.title(),
                    line={"color": engine_colors_trend.get(eng, "#94a3b8"), "width": 2},
                    marker={"size": 7},
                ))
            fig_trend.update_layout(
                height=280, yaxis_title="SOV %", yaxis_range=[0, 100],
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        st.divider()
        st.subheader("Coverage by Prompt Class")
        st.caption("% of probes in each Petra Labs class where brand is mentioned (averaged across engines)")
        class_rows = []
        for cls in ["C", "B", "seed", "A"]:
            cls_label = {"C": "Class C — Intent shift (how-to)",
                         "B": "Class B — Context edits",
                         "seed": "Seed (baseline)",
                         "A": "Class A — Surface edits"}[cls]
            cls_df = probes_df[probes_df["perturbation_class"] == cls]
            if cls_df.empty:
                continue
            rate = cls_df["brand_mentioned"].mean() * 100
            class_rows.append({"Class": cls_label, "Probes": len(cls_df),
                                "Mention rate %": round(rate, 1),
                                "Expected movement (Petra Labs)": {
                                    "C": "WJD 0.97 — highest", "B": "WJD 0.80 — high",
                                    "seed": "baseline", "A": "WJD 0.54 — lowest"}[cls]})
        if class_rows:
            st.dataframe(pd.DataFrame(class_rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Probe-by-Probe Log")
        fc1, fc2, fc3 = st.columns(3)
        filter_engine = fc1.selectbox("Engine", ["All"] + engines, key="ov_eng")
        filter_mentioned = fc2.selectbox("Result", ["All", "Mentioned ✓", "Not mentioned ✗"],
                                         index=0, key="ov_ment")
        filter_pt = fc3.selectbox("Prompt type", ["All"] + _PT_ORDER, key="ov_pt")
        fdf = probes_df.copy()
        if filter_engine != "All":
            fdf = fdf[fdf["engine"] == filter_engine]
        if filter_mentioned == "Mentioned ✓":
            fdf = fdf[fdf["brand_mentioned"]]
        elif filter_mentioned == "Not mentioned ✗":
            fdf = fdf[~fdf["brand_mentioned"]]
        if filter_pt != "All":
            fdf = fdf[fdf["perturbation_type"] == filter_pt]
        st.caption(f"Showing {len(fdf)} of {len(probes_df)} probes")
        for _, row in fdf.iterrows():
            icon = "✓" if row["brand_mentioned"] else "✗"
            color = "#10b981" if row["brand_mentioned"] else "#ef4444"
            pt = row.get("perturbation_type", "?")
            engine = row.get("engine", "")
            label = f'[{icon}] [{engine}] [{pt}] {row["probe_text"][:80]}{"…" if len(row["probe_text"]) > 80 else ""}'
            with st.expander(label):
                st.caption(f"**Full probe:** {row['probe_text']}")
                ctx = _safe_context(row.get("brand_context"))
                st.markdown(
                    f'<b style="color:{color};">{COMPANY_NAME} '
                    f'{"mentioned" if row["brand_mentioned"] else "not mentioned"}</b>'
                    + (f' — <i>"{ctx}"</i>' if ctx else ""),
                    unsafe_allow_html=True,
                )
                comps = _safe_json_list(row.get("competitors_mentioned"))
                if comps:
                    st.caption(f"Competitors: {', '.join(comps)}")
                cited = _safe_json_list(row.get("cited_urls"))
                if cited:
                    for u in cited[:6]:
                        st.markdown(f"  - [{u[:70]}]({u})")
                # Full response text (trimmed to 500 chars)
                resp_text = _extract_response_text(row.get("raw_response", ""))
                if resp_text:
                    with st.expander("↳ Full AI response", expanded=False):
                        preview = resp_text[:500]
                        if len(resp_text) > 500:
                            preview += f"\n\n…({len(resp_text) - 500} chars truncated)"
                        st.markdown(preview)

    # ── Tab 2: Prompt Heatmap ──────────────────────────────────────────────────
    with tab2:
        st.subheader("Brand Mention Rate by Prompt Type × Engine")
        st.caption(
            "Each cell = % of probes in that type where the engine mentioned "
            f"{COMPANY_NAME}. Filter by vertical to see how Lido performs on specific buying scenarios."
        )

        # Seed topic filter
        topic_options = ["All verticals"] + [
            _TOPIC_LABEL.get(t, t)
            for t in sorted(probes_df["seed_topic"].unique())
            if t != "general"
        ]
        _label_to_topic = {v: k for k, v in _TOPIC_LABEL.items()}
        selected_topic_label = st.selectbox("Vertical", topic_options, key="hm_topic")
        if selected_topic_label == "All verticals":
            hm_df = probes_df.copy()
        else:
            selected_topic = _label_to_topic.get(selected_topic_label, selected_topic_label)
            hm_df = probes_df[probes_df["seed_topic"] == selected_topic].copy()

        has_types = hm_df["perturbation_type"].nunique() > 1
        if not has_types:
            st.info("Run the full probe set to see the heatmap. Use `make run-lido` for all 60 probes.")
        else:
            pivot = (
                hm_df.groupby(["perturbation_type", "engine"])["brand_mentioned"]
                .mean()
                .mul(100)
                .unstack("engine")
                .fillna(0)
                .round(1)
            )
            ordered = [pt for pt in _PT_ORDER if pt in pivot.index]
            pivot = pivot.reindex(ordered)

            # Y-axis labels with class annotation
            y_labels = [
                f"{pt}  [{_PT_CLASS.get(pt, '?')}]" for pt in pivot.index
            ]

            fig_heat = go.Figure(go.Heatmap(
                z=pivot.values,
                x=[e.title() for e in pivot.columns],
                y=y_labels,
                colorscale=[[0, "#fee2e2"], [0.3, "#fef08a"], [0.6, "#bbf7d0"], [1, "#15803d"]],
                zmin=0, zmax=100,
                text=pivot.values,
                texttemplate="%{text:.0f}%",
                textfont={"size": 12},
                hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}%<extra></extra>",
            ))
            fig_heat.update_layout(
                height=max(400, len(pivot) * 38),
                margin=dict(l=180, r=40, t=20, b=40),
                xaxis_title="Engine",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_heat, use_container_width=True)

            st.divider()
            st.subheader("Overall mention rate by prompt type (averaged across engines)")
            avg_by_type = hm_df.groupby("perturbation_type")["brand_mentioned"].mean().mul(100)
            avg_ordered = avg_by_type.reindex([pt for pt in _PT_ORDER if pt in avg_by_type.index])
            colors_bar = [_CLASS_COLOR.get(_PT_CLASS.get(pt, "A"), "#94a3b8") for pt in avg_ordered.index]
            fig_bar = go.Figure(go.Bar(
                x=avg_ordered.values,
                y=[f"{pt} [{_PT_CLASS.get(pt,'?')}]" for pt in avg_ordered.index],
                orientation="h",
                marker_color=colors_bar,
                text=[f"{v:.0f}%" for v in avg_ordered.values],
                textposition="outside",
            ))
            fig_bar.update_layout(
                height=max(350, len(avg_ordered) * 32),
                xaxis_range=[0, 115],
                xaxis_title="Brand mention rate %",
                margin=dict(l=160, r=60, t=10, b=20),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            st.divider()
            st.subheader("Prompt map: which types give you the most coverage?")
            st.caption(
                "Petra Labs shows 5 prompt types cover 85% of citation space. "
                "Below: cumulative unique cited domains added by each prompt type (sorted by contribution)."
            )
            # Count unique cited_urls contributed by each perturbation_type
            all_cited: dict[str, set] = {}
            for _, row in hm_df.iterrows():
                pt = row.get("perturbation_type", "seed")
                urls = set(_safe_json_list(row.get("cited_urls")))
                all_cited.setdefault(pt, set()).update(urls)

            # Sort by unique contribution, then compute cumulative
            pt_sizes = sorted(all_cited.items(), key=lambda x: len(x[1]), reverse=True)
            seen: set = set()
            map_rows = []
            for pt, urls in pt_sizes:
                new_urls = urls - seen
                seen.update(urls)
                map_rows.append({
                    "Prompt type": pt,
                    "Class": _PT_CLASS.get(pt, "?"),
                    "Unique domains": len(urls),
                    "New domains added": len(new_urls),
                    "Cumulative total": len(seen),
                })
            if map_rows:
                st.dataframe(pd.DataFrame(map_rows), use_container_width=True, hide_index=True)

    # ── Tab 3: Citation Space ──────────────────────────────────────────────────
    with tab3:
        # Build domain aggregates once
        domain_to_types: dict[str, set] = {}
        domain_to_count: dict[str, int] = {}
        domain_to_engines: dict[str, set] = {}
        for _, row in probes_df.iterrows():
            pt = row.get("perturbation_type", "seed")
            eng = row.get("engine", "")
            domains = _safe_json_list(row.get("cited_domains"))
            for d in domains:
                d = d.strip()
                if not d:
                    continue
                domain_to_types.setdefault(d, set()).add(pt)
                domain_to_engines.setdefault(d, set()).add(eng)
                domain_to_count[d] = domain_to_count.get(d, 0) + 1

        comp_domains = [c.lower().rstrip("/") for c in COMPETITORS]

        # ── Source type distribution ───────────────────────────────────────────
        st.subheader("Citation Source Distribution")
        st.caption("What types of content do AI engines cite? This tells you where to publish.")
        type_counts: dict[str, int] = {}
        for d, cnt in domain_to_count.items():
            t = _classify_domain(d, BRAND_DOMAIN, comp_domains)
            type_counts[t] = type_counts.get(t, 0) + cnt

        if type_counts:
            fig_pie = go.Figure(go.Pie(
                labels=list(type_counts.keys()),
                values=list(type_counts.values()),
                marker={"colors": [_DOMAIN_TYPE_COLORS.get(k, "#94a3b8") for k in type_counts]},
                hole=0.4,
                textinfo="label+percent",
                hovertemplate="%{label}: %{value} citations (%{percent})<extra></extra>",
            ))
            fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0),
                                  showlegend=True, legend={"orientation": "h"})
            st.plotly_chart(fig_pie, use_container_width=True)

            # Action callout based on dominant type
            dominant_type = max(type_counts, key=type_counts.get)
            action_callouts = {
                "review platform": f"**{dominant_type.title()} content dominates AI citations** — prioritise G2, Capterra, and Gartner Peer Insights listings.",
                "general web": f"**General web content dominates** — AI engines are pulling from blog posts and articles. Publish more structured comparison and listicle content.",
                "competitor": f"**Competitor pages dominate AI citations** — create direct comparison and 'alternatives' pages to win citation share.",
                "community": f"**Community content dominates** — participate in Reddit and Quora discussions where your product solves real problems.",
                "brand": f"**Your own content is well-cited** — continue publishing and expand to review platforms for broader coverage.",
                "tech media": f"**Tech media dominates** — pursue press coverage in TechCrunch, Forbes, and VentureBeat.",
            }
            st.info(action_callouts.get(dominant_type, f"**{dominant_type}** content dominates AI citations."))

        st.divider()
        st.subheader("Stable Domains")
        st.caption(
            "Domains cited across ≥3 different prompt types — the citation core "
            "AI engines return regardless of how the question is framed. These are your top placement targets."
        )
        stable = [
            {
                "Domain": d,
                "Type": _classify_domain(d, BRAND_DOMAIN, comp_domains),
                "Prompt types": len(pts),
                "Engines": len(domain_to_engines.get(d, set())),
                "Total citations": domain_to_count[d],
                "Types list": ", ".join(sorted(pts)),
            }
            for d, pts in domain_to_types.items()
            if len(pts) >= 3
        ]
        stable.sort(key=lambda x: (-x["Prompt types"], -x["Total citations"]))
        if stable:
            stable_df = pd.DataFrame(stable)
            st.dataframe(stable_df.drop(columns=["Types list"]), use_container_width=True, hide_index=True)
        else:
            st.info("Run the full probe set to populate stable domains — need ≥3 prompt type citations per domain.")

        st.divider()
        st.subheader("Top 25 Cited Domains")
        st.caption("Color = source type. Green = review platform (priority for listings). Red = competitor.")
        all_domains: dict[str, int] = {}
        for d, cnt in domain_to_count.items():
            if d:
                all_domains[d] = cnt
        if all_domains:
            top_domains = sorted(all_domains.items(), key=lambda x: -x[1])[:25]
            top_df = pd.DataFrame(top_domains, columns=["Domain", "Citations"])
            top_df["Type"] = top_df["Domain"].apply(lambda d: _classify_domain(d, BRAND_DOMAIN, comp_domains))
            fig_top = go.Figure(go.Bar(
                x=top_df["Citations"], y=top_df["Domain"],
                orientation="h",
                marker_color=[_DOMAIN_TYPE_COLORS.get(t, "#94a3b8") for t in top_df["Type"]],
                text=top_df["Citations"], textposition="outside",
                customdata=top_df["Type"],
                hovertemplate="<b>%{y}</b><br>Citations: %{x}<br>Type: %{customdata}<extra></extra>",
            ))
            fig_top.update_layout(
                height=600, margin=dict(l=180, r=80, t=10, b=10),
                xaxis_title="Total citations",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_top, use_container_width=True)

        st.divider()
        st.subheader("Citation Volume by Prompt Class")
        class_cites = {}
        for _, row in probes_df.iterrows():
            cls = row.get("perturbation_class", "seed")
            urls = _safe_json_list(row.get("cited_urls"))
            class_cites[cls] = class_cites.get(cls, 0) + len(urls)
        if class_cites:
            cls_labels = {"C": "Class C (Intent)", "B": "Class B (Context)", "seed": "Seed", "A": "Class A (Surface)"}
            fig_cls = go.Figure(go.Bar(
                x=[cls_labels.get(c, c) for c in class_cites],
                y=list(class_cites.values()),
                marker_color=[_CLASS_COLOR.get(c, "#94a3b8") for c in class_cites],
                text=list(class_cites.values()),
                textposition="outside",
            ))
            fig_cls.update_layout(height=280, yaxis_title="Total cited URLs",
                                  margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_cls, use_container_width=True)

    # ── Tab 4: Competitive Benchmark ───────────────────────────────────────────
    with tab4:
        st.subheader("Competitor Displacement Analysis")
        st.caption(
            f"Probes where a competitor is mentioned but {COMPANY_NAME} is not = displacement. "
            "Higher = more search traffic this competitor captures that you don't."
        )

        probes_df["_comps"] = probes_df["competitors_mentioned"].apply(_safe_json_list)
        has_any_comp = probes_df["_comps"].str.len().gt(0).any()

        if not has_any_comp:
            st.info("No competitor mentions detected yet. Run more probes or check competitor list in profile.yaml.")
        else:
            # Overall competitor leaderboard
            comp_counts: dict[str, int] = {}
            disp_counts: dict[str, int] = {}
            for _, row in probes_df.iterrows():
                comps = _safe_json_list(row.get("competitors_mentioned"))
                mentioned = row["brand_mentioned"]
                for c in comps:
                    comp_counts[c] = comp_counts.get(c, 0) + 1
                    if not mentioned:
                        disp_counts[c] = disp_counts.get(c, 0) + 1

            leaderboard = [
                {
                    "Competitor": c,
                    "Total mentions": comp_counts[c],
                    "Displacement (brand absent)": disp_counts.get(c, 0),
                    "Displacement rate %": round(disp_counts.get(c, 0) / comp_counts[c] * 100, 1),
                }
                for c in sorted(comp_counts, key=lambda x: -disp_counts.get(x, 0))
            ]
            lead_df = pd.DataFrame(leaderboard)
            st.dataframe(lead_df, use_container_width=True, hide_index=True)

            # Displacement by engine
            st.divider()
            st.subheader("Displacement by Engine")
            engine_disp = {}
            for _, row in probes_df.iterrows():
                if not row["brand_mentioned"]:
                    eng = row["engine"]
                    comps = _safe_json_list(row.get("competitors_mentioned"))
                    engine_disp[eng] = engine_disp.get(eng, 0) + len(comps)
            if engine_disp:
                fig_ed = go.Figure(go.Bar(
                    x=list(engine_disp.keys()),
                    y=list(engine_disp.values()),
                    marker_color=["#ef4444" if v == max(engine_disp.values()) else "#f59e0b"
                                  for v in engine_disp.values()],
                    text=list(engine_disp.values()), textposition="outside",
                ))
                fig_ed.update_layout(height=260, yaxis_title="Competitor mentions where brand absent",
                                     margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig_ed, use_container_width=True)

            # Displacement by prompt type
            st.divider()
            st.subheader("Displacement by Prompt Type")
            st.caption("Which prompt framings give competitors the most advantage?")
            pt_disp: dict[str, int] = {}
            pt_total: dict[str, int] = {}
            for _, row in probes_df.iterrows():
                pt = row.get("perturbation_type", "seed")
                pt_total[pt] = pt_total.get(pt, 0) + 1
                if not row["brand_mentioned"]:
                    comps = _safe_json_list(row.get("competitors_mentioned"))
                    pt_disp[pt] = pt_disp.get(pt, 0) + len(comps)
            if pt_disp:
                pt_disp_df = pd.DataFrame([
                    {"Prompt type": pt,
                     "Class": _PT_CLASS.get(pt, "?"),
                     "Displacement events": pt_disp.get(pt, 0),
                     "Probes run": pt_total.get(pt, 0)}
                    for pt in [p for p in _PT_ORDER if p in pt_total]
                ]).sort_values("Displacement events", ascending=False)
                st.dataframe(pt_disp_df, use_container_width=True, hide_index=True)

            # SOV comparison chart
            st.divider()
            st.subheader(f"SOV: {COMPANY_NAME} vs. top competitors by engine")
            # Sort competitors by total mentions so we show the most impactful
            comp_list_sorted = sorted(comp_counts.keys(), key=lambda c: -comp_counts[c])[:6]
            fig_sov_comp = go.Figure()
            brand_by_eng = {
                eng: int(probes_df[probes_df["engine"] == eng]["brand_mentioned"].sum())
                for eng in engines
            }
            fig_sov_comp.add_trace(go.Bar(
                name=COMPANY_NAME, x=[e.title() for e in engines],
                y=[brand_by_eng.get(e, 0) for e in engines],
                marker_color="#E09A3F",
            ))
            for comp in comp_list_sorted:
                comp_by_eng = {}
                for _, row in probes_df.iterrows():
                    if comp in _safe_json_list(row.get("competitors_mentioned")):
                        comp_by_eng[row["engine"]] = comp_by_eng.get(row["engine"], 0) + 1
                fig_sov_comp.add_trace(go.Bar(
                    name=comp.split(".")[0].title(), x=[e.title() for e in engines],
                    y=[comp_by_eng.get(e, 0) for e in engines],
                    marker_color="#DFD9CE",
                ))
            fig_sov_comp.update_layout(
                barmode="group", height=340, yaxis_title="Times mentioned",
                margin=dict(l=0, r=0, t=20, b=0),
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "font": {"size": 11}},
            )
            st.plotly_chart(fig_sov_comp, use_container_width=True)

            # ── Competitor spotlight ───────────────────────────────────────────
            st.divider()
            st.subheader("Competitor Spotlight")
            st.caption("Pick a competitor to see exactly where they beat you and what content would close the gap.")
            spotlight_comp = st.selectbox(
                "Competitor",
                options=comp_list_sorted,
                format_func=lambda c: c.split(".")[0].title(),
                key="comp_spotlight",
            )
            sp_rows = probes_df.copy()
            sp_rows["_sp_comp"] = sp_rows["competitors_mentioned"].apply(
                lambda v: spotlight_comp in _safe_json_list(v)
            )

            # Where competitor wins (mentioned, brand absent)
            comp_wins = sp_rows[sp_rows["_sp_comp"] & ~sp_rows["brand_mentioned"]]
            # Where brand co-appears with competitor
            comp_tied = sp_rows[sp_rows["_sp_comp"] & sp_rows["brand_mentioned"]]

            col_w, col_t = st.columns(2)
            with col_w:
                st.metric(f"{spotlight_comp.split('.')[0].title()} wins (brand absent)", len(comp_wins))
            with col_t:
                st.metric(f"Co-mentioned with {COMPANY_NAME}", len(comp_tied))

            # Wins by vertical
            if not comp_wins.empty:
                wins_by_vert = comp_wins.groupby("seed_topic").size().reset_index(name="wins")
                wins_by_vert["Vertical"] = wins_by_vert["seed_topic"].map(
                    lambda t: _TOPIC_LABEL.get(t, t)
                )
                wins_by_vert = wins_by_vert.sort_values("wins", ascending=False)
                fig_sp_vert = go.Figure(go.Bar(
                    x=wins_by_vert["wins"], y=wins_by_vert["Vertical"],
                    orientation="h", marker_color="#ef4444",
                    text=wins_by_vert["wins"], textposition="outside",
                ))
                fig_sp_vert.update_layout(
                    height=max(250, len(wins_by_vert) * 30),
                    title_text=f"{spotlight_comp.split('.')[0].title()} displacement by vertical",
                    xaxis_title="Times displacing you",
                    margin=dict(l=160, r=60, t=40, b=10),
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig_sp_vert, use_container_width=True)

                # Wins by prompt type
                wins_by_pt = comp_wins.groupby("perturbation_type").size().reset_index(name="wins")
                wins_by_pt["Class"] = wins_by_pt["perturbation_type"].map(
                    lambda p: _PT_CLASS.get(p, "?")
                )
                wins_by_pt = wins_by_pt.sort_values("wins", ascending=False)
                fig_sp_pt = go.Figure(go.Bar(
                    x=wins_by_pt["wins"],
                    y=[f"{r['perturbation_type']} [{r['Class']}]" for _, r in wins_by_pt.iterrows()],
                    orientation="h",
                    marker_color=[_CLASS_COLOR.get(c, "#94a3b8") for c in wins_by_pt["Class"]],
                    text=wins_by_pt["wins"], textposition="outside",
                ))
                fig_sp_pt.update_layout(
                    height=max(250, len(wins_by_pt) * 30),
                    title_text=f"{spotlight_comp.split('.')[0].title()} displacement by prompt type",
                    xaxis_title="Times displacing you",
                    margin=dict(l=200, r=60, t=40, b=10),
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig_sp_pt, use_container_width=True)

                # Content recommendation
                top_vert = wins_by_vert.iloc[0]["Vertical"] if len(wins_by_vert) else ""
                top_pt = wins_by_pt.iloc[0]["perturbation_type"] if len(wins_by_pt) else ""
                comp_short = spotlight_comp.split(".")[0].title()
                st.info(
                    f"**Recommended content to recapture from {comp_short}:**  \n"
                    f"1. Publish an 'Alternatives to {comp_short}' comparison page — directly targets the "
                    f"`competitor` probe type where {comp_short} wins most.  \n"
                    f"2. Create a {top_vert} vertical landing page with explicit capability language — "
                    f"{comp_short} leads you {wins_by_vert.iloc[0]['wins']}× in this vertical.  \n"
                    f"3. Target `{top_pt}` prompt framing in your content — this is where "
                    f"{comp_short} outperforms you most."
                )

    # ── Tab 5: Opportunities ────────────────────────────────────────────────────
    with tab5:
        # ── "This week" action brief ──────────────────────────────────────────
        st.subheader("This Week's Playbook")

        # Find verticals with zero visibility
        zero_vert = [
            _TOPIC_LABEL.get(t, t)
            for t in sorted(probes_df["seed_topic"].unique())
            if t != "general"
            and not probes_df[probes_df["seed_topic"] == t]["brand_mentioned"].any()
        ]
        # Find top-displacement competitor
        comp_disp_all: dict[str, int] = {}
        for _, r in probes_df.iterrows():
            if not r["brand_mentioned"]:
                for c in _safe_json_list(r.get("competitors_mentioned")):
                    comp_disp_all[c] = comp_disp_all.get(c, 0) + 1
        top_displacer = max(comp_disp_all, key=comp_disp_all.get) if comp_disp_all else None
        # Find engines with zero visibility
        zero_engines = [
            eng for eng in engines
            if not probes_df[probes_df["engine"] == eng]["brand_mentioned"].any()
        ]

        actions = []
        if zero_engines:
            actions.append(("🔴 Zero visibility on " + " + ".join(e.title() for e in zero_engines),
                            "These engines have zero brand awareness. Prioritise publishing content on "
                            "G2, Capterra, and Reddit — AI engines heavily cite these review platforms."))
        if zero_vert:
            for zv in zero_vert[:3]:
                actions.append((f"🟡 No mentions in **{zv}** vertical",
                                f"Publish a vertical-specific landing page targeting {zv.lower()} use cases "
                                "with explicit product capability language AI engines can cite."))
        if top_displacer:
            clean_comp = top_displacer.split(".")[0].title()
            n_disp = comp_disp_all[top_displacer]
            actions.append((f"🟠 {clean_comp} displacing you {n_disp}× across all engines",
                            f"Publish an 'Alternatives to {clean_comp}' comparison page and submit it to "
                            "G2 and Capterra for cross-linking."))
        if not actions:
            actions.append(("✅ No critical gaps", "Brand is visible across all engines and verticals."))

        for title, desc in actions:
            st.markdown(f"**{title}**  \n{desc}")
        st.divider()

        st.subheader("SERP × AI Citation Gaps")
        st.caption(
            "Pages that AI engines cite in probe responses AND appear in your SERP citation graph — "
            f"but where {COMPANY_NAME} is absent. These are your highest-leverage targets."
        )

        if xref_df.empty:
            st.info("No cross-reference data. Run `make run-lido` to populate.")
        else:
            gap_df = xref_df[xref_df["action_priority"].isin(["critical", "high"])].copy()
            if gap_df.empty:
                st.success("No critical/high gaps found — brand is present on all AI-cited SERP pages.")
            else:
                priority_colors = {"critical": "#ef4444", "high": "#f59e0b"}
                for _, row in gap_df.head(25).iterrows():
                    color = priority_colors.get(row["action_priority"], "#6b7280")
                    engines_cited = _safe_json_list(row.get("engines_citing_url"))
                    st.markdown(
                        f'<span style="background:{color};color:white;padding:2px 8px;'
                        f'border-radius:4px;font-size:0.75rem;margin-right:6px;">'
                        f'{row["action_priority"].upper()}</span>'
                        f'**[{row["url"][:80]}]({row["url"]})**<br>'
                        f'<span style="color:#6b7280;font-size:0.8rem;">'
                        f'SERP weight: {row["serp_weighted_score"]:.2f} | '
                        f'Cited by: {", ".join(engines_cited) or "none"}</span>',
                        unsafe_allow_html=True,
                    )
                    st.write("")

        st.divider()
        st.subheader("Opportunity by Prompt Type")
        st.caption(
            "Which prompt framings surface pages you're absent from? "
            "Target these prompt types to understand where you're losing AI citations."
        )
        type_gaps: dict[str, dict] = {}
        for _, row in probes_df.iterrows():
            if not row["brand_mentioned"]:
                pt = row.get("perturbation_type", "seed")
                cited = _safe_json_list(row.get("cited_urls"))
                comps = _safe_json_list(row.get("competitors_mentioned"))
                if pt not in type_gaps:
                    type_gaps[pt] = {"probes": 0, "cited_urls": set(), "competitor_events": 0}
                type_gaps[pt]["probes"] += 1
                type_gaps[pt]["cited_urls"].update(cited)
                type_gaps[pt]["competitor_events"] += len(comps)

        if type_gaps:
            opp_rows = [
                {
                    "Prompt type": pt,
                    "Class": _PT_CLASS.get(pt, "?"),
                    "Missed probes": d["probes"],
                    "Unique URLs cited (you absent)": len(d["cited_urls"]),
                    "Competitor mentions while absent": d["competitor_events"],
                }
                for pt, d in sorted(
                    type_gaps.items(),
                    key=lambda x: -(len(x[1]["cited_urls"]) + x[1]["competitor_events"])
                )
            ]
            opp_df = pd.DataFrame(opp_rows)
            st.dataframe(opp_df, use_container_width=True, hide_index=True)

            # Recommended actions by top opportunity prompt type
            if opp_rows:
                top_pt = opp_rows[0]["Prompt type"]
                top_cls = opp_rows[0]["Class"]
                st.divider()
                st.subheader(f"Top opportunity: `{top_pt}` (Class {top_cls})")
                action_map = {
                    "how-to": "Create how-to content and tutorials that rank for instructional queries",
                    "pain": "Publish pain-point landing pages targeting workflow friction keywords",
                    "persona-regulated": "Build compliance-focused content for regulated-industry buyers",
                    "competitor": "Create direct comparison pages and 'alternatives to' content",
                    "use-case": "Develop use-case specific landing pages for your key verticals",
                    "requirements": "Create feature comparison content addressing specific technical requirements",
                    "price-budget": "Add pricing transparency content and SMB-focused landing pages",
                    "persona-casual": "Create startup/SMB focused content and case studies",
                    "price-premium": "Develop ROI/enterprise content highlighting accuracy and scale",
                    "seed": "Improve your core category presence — aim for G2 and Capterra listings",
                    "simplify": "Ensure bare-keyword presence: optimize category pages",
                    "best": "Target 'best X software' listicles and comparison articles",
                    "recommend": "Get recommended on Reddit, forums, and community sites",
                    "spanish": "Expand Spanish-language content for Latin American market",
                    "typo": "Broad match keyword coverage — low priority",
                }
                action = action_map.get(top_pt, "Improve content for this query framing")
                st.info(f"**Recommended action:** {action}")

                # Show the URLs being cited in this prompt type while you're absent
                absent_urls = type_gaps[top_pt]["cited_urls"]
                if absent_urls:
                    st.write(f"Pages cited in `{top_pt}` probes where {COMPANY_NAME} is absent:")
                    for u in sorted(absent_urls)[:10]:
                        st.markdown(f"  - [{u[:80]}]({u})")

        # ── Vertical gap deep-dive ─────────────────────────────────────────────
        zero_topics_raw = [
            t for t in sorted(probes_df["seed_topic"].unique())
            if t != "general"
            and not probes_df[probes_df["seed_topic"] == t]["brand_mentioned"].any()
        ]
        if zero_topics_raw:
            st.divider()
            st.subheader("Zero-Visibility Vertical Deep-Dive")
            st.caption(
                "Pages AI engines cite in verticals where your brand never appears. "
                "These are your highest-priority content placement targets."
            )
            selected_zero = st.selectbox(
                "Zero-visibility vertical",
                options=zero_topics_raw,
                format_func=lambda t: _TOPIC_LABEL.get(t, t),
                key="zero_vert_drill",
            )
            zero_df = probes_df[
                (probes_df["seed_topic"] == selected_zero) & ~probes_df["brand_mentioned"]
            ]

            # Collect all cited URLs + their competitors in this vertical
            vert_urls: dict[str, dict] = {}
            for _, r in zero_df.iterrows():
                cited = _safe_json_list(r.get("cited_urls"))
                comps = _safe_json_list(r.get("competitors_mentioned"))
                eng = r.get("engine", "")
                pt = r.get("perturbation_type", "seed")
                for u in cited:
                    if not u:
                        continue
                    if u not in vert_urls:
                        vert_urls[u] = {"engines": set(), "pts": set(), "comps": set()}
                    vert_urls[u]["engines"].add(eng)
                    vert_urls[u]["pts"].add(pt)
                    vert_urls[u]["comps"].update(comps)

            if vert_urls:
                vert_url_rows = sorted(
                    vert_urls.items(),
                    key=lambda x: -(len(x[1]["engines"]) * 10 + len(x[1]["pts"])),
                )
                for u, meta in vert_url_rows[:15]:
                    engs_str = ", ".join(sorted(meta["engines"]))
                    comps_str = ", ".join(sorted(meta["comps"])) if meta["comps"] else "none"
                    st.markdown(
                        f'**[{u[:80]}]({u})**  \n'
                        f'<span style="color:#6b7280;font-size:0.8rem;">'
                        f'Engines citing: {engs_str} | '
                        f'Prompt types: {len(meta["pts"])} | '
                        f'Competitors co-cited: {comps_str[:60]}</span>',
                        unsafe_allow_html=True,
                    )
                    st.write("")
            else:
                st.info(f"No external citations found for the {_TOPIC_LABEL.get(selected_zero, selected_zero)} vertical.")

    # ── Tab 6: Sponsored Ads ───────────────────────────────────────────────────
    with tab6:
        st.subheader("Sponsored Ad Intelligence")
        st.caption(
            "Domains appearing in Google paid ad slots for each probe query. "
            "Amber = brand running its own ads · Red = competitor bidding on your keywords."
        )

        google_df = probes_df[probes_df["engine"] == "google"].copy()
        if google_df.empty:
            st.info("No Google AI Overview data for this run. Run with VALUESERP_KEY configured.")
        else:
            # Parse sponsored_domains JSON
            def _parse_sponsored(val):
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                try:
                    parsed = json.loads(val)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    return []

            google_df["_sponsored"] = google_df.get("sponsored_domains", pd.Series(dtype=object)).apply(_parse_sponsored)

            # Flatten all sponsored domains
            all_sponsored: dict[str, int] = {}
            for domains in google_df["_sponsored"]:
                for d in domains:
                    d = d.lstrip("www.").split("/")[0].strip() if d else ""
                    if d:
                        all_sponsored[d] = all_sponsored.get(d, 0) + 1

            if not all_sponsored:
                st.info(
                    "No sponsored ad domains captured yet. "
                    "Ads don't appear on every query — run more probes to populate this view."
                )
            else:
                comp_domains_lower = [c.lower() for c in COMPETITORS]

                # Summary metrics
                total_ad_events = sum(all_sponsored.values())
                brand_ad_count = sum(v for k, v in all_sponsored.items() if BRAND_SLUG.lower() in k.lower())
                comp_ad_count = sum(
                    v for k, v in all_sponsored.items()
                    if any(c in k.lower() for c in comp_domains_lower)
                )

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Total ad appearances", total_ad_events)
                mc2.metric(f"{COMPANY_NAME} self-bids", brand_ad_count)
                mc3.metric("Competitor bids on your terms", comp_ad_count)

                # Bar chart of sponsored domain frequency
                sp_rows = sorted(all_sponsored.items(), key=lambda x: -x[1])
                sp_df = pd.DataFrame(sp_rows, columns=["Domain", "Ad appearances"])
                sp_df["color"] = sp_df["Domain"].apply(
                    lambda d: "#E09A3F" if BRAND_SLUG.lower() in d.lower() else
                              "#ef4444" if any(c in d.lower() for c in comp_domains_lower) else "#4B5340"
                )

                fig_sp = go.Figure(go.Bar(
                    x=sp_df["Ad appearances"],
                    y=sp_df["Domain"],
                    orientation="h",
                    marker_color=sp_df["color"].tolist(),
                    text=sp_df["Ad appearances"],
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Ad appearances: %{x}<extra></extra>",
                ))
                fig_sp.update_layout(
                    height=max(300, len(sp_df) * 36),
                    margin=dict(l=180, r=80, t=20, b=10),
                    xaxis_title="Probe queries with this ad domain",
                    yaxis=dict(autorange="reversed"),
                    paper_bgcolor="#FBF9F4",
                    plot_bgcolor="#FBF9F4",
                )
                st.plotly_chart(fig_sp, use_container_width=True)

                # Probe-level table
                st.divider()
                st.subheader("Probes with Sponsored Ads")
                sp_probe_rows = []
                for _, row in google_df.iterrows():
                    domains = row["_sponsored"]
                    if not domains:
                        continue
                    sp_probe_rows.append({
                        "Probe": row["probe_text"][:70],
                        "Probe ID": row["probe_id"],
                        "Ad domains": ", ".join(d.lstrip("www.") for d in domains),
                        "Brand self-bid": any(BRAND_SLUG.lower() in d.lower() for d in domains),
                        "Competitor bid": any(
                            any(c in d.lower() for c in comp_domains_lower) for d in domains
                        ),
                    })
                if sp_probe_rows:
                    st.dataframe(pd.DataFrame(sp_probe_rows), use_container_width=True, hide_index=True)
                else:
                    st.info("No sponsored domains found in individual probe results.")


# ──────────────────────────────────────────────────────────────────────────────
# SEO Ranks page
# ──────────────────────────────────────────────────────────────────────────────

def page_seo_ranks(run_date):
    st.title("SEO Ranks")
    st.caption(
        f"Organic search positions for **{COMPANY_NAME}** and top competitors — {run_date}. "
        "Data sourced from ValueSERP organic results."
    )

    serp = load_serp_results(run_date)
    if serp.empty:
        st.warning("No SERP data for this run date.")
        return

    brand_serp = serp[serp["domain"] == BRAND_DOMAIN][["query", "position"]].sort_values("position")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Queries tracked", serp["query"].nunique())
    m2.metric(f"{BRAND_DOMAIN} ranking", len(brand_serp))
    if not brand_serp.empty:
        m3.metric("Best position", int(brand_serp["position"].min()))
        m4.metric("Avg position", f"{brand_serp['position'].mean():.1f}")
    else:
        m3.metric("Best position", "—")
        m4.metric("Avg position", "—")

    st.divider()

    # ── Brand position table ───────────────────────────────────────────────────
    st.subheader(f"{BRAND_DOMAIN} SERP Positions")
    if brand_serp.empty:
        st.info(f"{BRAND_DOMAIN} does not appear in organic results for any tracked query this run.")
    else:
        st.dataframe(brand_serp.rename(columns={"query": "Query", "position": "Position"}),
                     use_container_width=True, hide_index=True)

    st.divider()

    # ── Position heatmap: query × domain ──────────────────────────────────────
    st.subheader("Position Heatmap")
    st.caption("Position by query (0 = not ranking). Amber = brand, olive = competitor. Lower number = better.")

    top_domains = serp.groupby("domain").size().sort_values(ascending=False).head(9).index.tolist()
    if BRAND_DOMAIN not in top_domains:
        top_domains = [BRAND_DOMAIN] + top_domains[:8]

    pivot = (
        serp[serp["domain"].isin(top_domains)]
        .pivot_table(index="query", columns="domain", values="position", aggfunc="min")
        .fillna(0)
        .astype(int)
    )
    if BRAND_DOMAIN in pivot.columns:
        cols = [BRAND_DOMAIN] + [c for c in pivot.columns if c != BRAND_DOMAIN]
        pivot = pivot[cols]

    short_queries = [q[:50] + "…" if len(q) > 50 else q for q in pivot.index]

    fig_heat = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=short_queries,
        colorscale=[[0, "#FBF9F4"], [0.15, "#DFD9CE"], [0.5, "#E09A3F"], [1, "#362C24"]],
        zmin=0, zmax=15,
        text=[[str(v) if v > 0 else "—" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="<b>%{y}</b><br>%{x}: position %{z}<extra></extra>",
        reversescale=True,
    ))
    fig_heat.update_layout(
        height=max(400, len(pivot) * 30),
        margin=dict(l=320, r=40, t=20, b=80),
        xaxis=dict(tickangle=-35),
        yaxis=dict(autorange="reversed"),
        paper_bgcolor="#FBF9F4",
        plot_bgcolor="#FBF9F4",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    st.divider()

    # ── Keyword gap: queries where brand is absent ─────────────────────────────
    st.subheader("Keyword Opportunities")
    st.caption(f"Queries where {BRAND_DOMAIN} is not in organic results, sorted by competitor density")

    brand_queries = set(serp[serp["domain"] == BRAND_DOMAIN]["query"])
    gap_queries = set(serp["query"]) - brand_queries

    if not gap_queries:
        st.success(f"{BRAND_DOMAIN} appears in organic results for every tracked query.")
    else:
        gap_rows = []
        for q in gap_queries:
            q_df = serp[serp["query"] == q]
            comp_domains = [d for d in q_df["domain"] if any(c.lower() in d.lower() for c in COMPETITORS)]
            best_comp_pos = q_df["position"].min()
            gap_rows.append({
                "Query": q,
                "Domains ranking": len(q_df),
                "Competitor domains": ", ".join(comp_domains[:3]) or "none",
                "Best competing position": int(best_comp_pos),
            })
        gap_rows.sort(key=lambda r: -r["Domains ranking"])
        st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Domain frequency bar chart ─────────────────────────────────────────────
    st.subheader("Most Frequent SERP Domains")
    st.caption("Amber = brand · Red = competitor · Olive = other. Number = appearances across all tracked queries.")

    domain_freq = (
        serp.groupby("domain")
        .agg(appearances=("query", "count"), best_position=("position", "min"))
        .sort_values("appearances", ascending=False)
        .head(20)
        .reset_index()
    )
    domain_freq["color"] = domain_freq["domain"].apply(
        lambda d: "#E09A3F" if d == BRAND_DOMAIN else
                  "#ef4444" if any(c.lower() in d.lower() for c in COMPETITORS) else "#4B5340"
    )

    fig_freq = go.Figure(go.Bar(
        x=domain_freq["appearances"],
        y=domain_freq["domain"],
        orientation="h",
        marker_color=domain_freq["color"].tolist(),
        text=domain_freq["appearances"],
        textposition="outside",
        customdata=domain_freq["best_position"],
        hovertemplate="<b>%{y}</b><br>Appearances: %{x}<br>Best position: %{customdata}<extra></extra>",
    ))
    fig_freq.update_layout(
        height=520,
        margin=dict(l=200, r=80, t=20, b=10),
        xaxis_title="Query appearances",
        yaxis=dict(autorange="reversed"),
        paper_bgcolor="#FBF9F4",
        plot_bgcolor="#FBF9F4",
    )
    st.plotly_chart(fig_freq, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# Ambrook CSS
# ──────────────────────────────────────────────────────────────────────────────

def _ambrook_css() -> str:
    return """
<style>
/* ── Ambrook Heartland Design System ── */

/* Main canvas — warm parchment */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main { background-color: #FBF9F4 !important; }
[data-testid="stHeader"] { background: transparent !important; }

/* Ensure all main-area text stays readable on parchment */
[data-testid="stMain"] p,
[data-testid="stMain"] span,
[data-testid="stMain"] label,
[data-testid="stMain"] li,
[data-testid="stMain"] td,
[data-testid="stMain"] div { color: #1A1C19; }

/* Sidebar — olive drab background, parchment text */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div { background-color: #4B5340 !important; }

/* Sidebar: only target visible text nodes, not everything */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] [data-testid="stMarkdown"] p { color: #FBF9F4 !important; }

/* Sidebar selectbox — the collapsed value pill */
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] span,
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] div { color: #1A1C19 !important; }

/* Sidebar dividers */
[data-testid="stSidebar"] hr { border-color: rgba(251,249,244,0.2) !important; }

/* Headers */
h1, h2, h3 { color: #1A1C19 !important; font-weight: 500; letter-spacing: 0.03em; }
h4, h5, h6 { color: #362C24 !important; font-weight: 500; }

/* Metric cards */
[data-testid="stMetricLabel"] {
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    font-size: 11px !important;
    color: #362C24 !important;
}
[data-testid="stMetricValue"] { color: #1A1C19 !important; font-size: 1.4rem !important; }
[data-testid="stMetricDelta"] { color: #4B5340 !important; }

/* Tabs — amber active underline */
.stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid #DFD9CE; }
.stTabs [data-baseweb="tab"] { color: #362C24 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    border-bottom: 3px solid #E09A3F !important;
    color: #1A1C19 !important;
    font-weight: 600;
}

/* Expanders */
.stExpander { border: 1px solid #DFD9CE !important; border-radius: 6px; }

/* Dataframes */
[data-testid="stDataFrame"] { border: 1px solid #DFD9CE; border-radius: 4px; }

/* Buttons */
.stButton > button {
    background: #E09A3F !important;
    color: #1A1C19 !important;
    border: none !important;
    font-weight: 600;
    border-radius: 4px;
}
.stButton > button:hover { background: #c88835 !important; }

/* Code blocks */
[data-testid="stCode"] { background: #FBF9F4 !important; border: 1px solid #DFD9CE; }
</style>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Report generator
# ──────────────────────────────────────────────────────────────────────────────

def _generate_weekly_report(run_date) -> str:
    """Generate a markdown weekly visibility report for the current run date."""
    probes_df = load_ae_probe_results(run_date)
    xref_df = load_cross_reference(run_date)

    if probes_df.empty:
        return f"# Elmo Weekly Report — {run_date}\n\nNo probe data for this run date.\n"

    probes_df = _ensure_probe_cols(probes_df)
    engines = sorted(probes_df["engine"].unique().tolist())
    n_probes = len(probes_df)
    n_mentions = int(probes_df["brand_mentioned"].sum())
    sov_pct = n_mentions / n_probes * 100 if n_probes else 0
    vis_score, score_comps = _compute_visibility_score(probes_df, engines)

    lines: list[str] = [
        f"# Elmo AI Visibility Report — {COMPANY_NAME}",
        f"**Run date:** {run_date}  ",
        f"**Generated:** {date.today()}",
        "",
        "---",
        "",
        f"## Visibility Score: {vis_score:.1f}/100",
        "",
        "| Component | Score |",
        "|---|---|",
    ]
    for k, v in score_comps.items():
        lines.append(f"| {k} | {v:.1f}% |")

    lines += [
        "",
        f"**Overall SOV:** {sov_pct:.1f}% ({n_mentions}/{n_probes} probes)",
        "",
        "---",
        "",
        "## SOV by Engine",
        "",
        "| Engine | Mentions | Probes | SOV % |",
        "|---|---|---|---|",
    ]
    for eng in engines:
        e_df = probes_df[probes_df["engine"] == eng]
        ment = int(e_df["brand_mentioned"].sum())
        tot = len(e_df)
        pct = ment / tot * 100 if tot else 0
        lines.append(f"| {eng.title()} | {ment} | {tot} | {pct:.1f}% |")

    lines += [
        "",
        "---",
        "",
        "## Visibility by Vertical",
        "",
        "| Vertical | SOV % | Best Engine |",
        "|---|---|---|",
    ]
    for topic in sorted(probes_df["seed_topic"].unique()):
        if topic == "general":
            continue
        t_df = probes_df[probes_df["seed_topic"] == topic]
        ment = int(t_df["brand_mentioned"].sum())
        tot = len(t_df)
        pct = ment / tot * 100 if tot else 0
        best = max(engines, key=lambda e: t_df[t_df["engine"] == e]["brand_mentioned"].mean())
        best_pct = t_df[t_df["engine"] == best]["brand_mentioned"].mean() * 100
        label = _TOPIC_LABEL.get(topic, topic)
        lines.append(f"| {label} | {pct:.0f}% | {best.title()} ({best_pct:.0f}%) |")

    # Competitor displacement
    comp_disp: dict[str, int] = {}
    for _, r in probes_df.iterrows():
        if not r["brand_mentioned"]:
            for c in _safe_json_list(r.get("competitors_mentioned")):
                comp_disp[c] = comp_disp.get(c, 0) + 1
    if comp_disp:
        lines += [
            "",
            "---",
            "",
            "## Top Competitor Displacements",
            "",
            "| Competitor | Times displacing brand |",
            "|---|---|",
        ]
        for c, n in sorted(comp_disp.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"| {c.split('.')[0].title()} | {n} |")

    # This week's playbook
    zero_vert = [
        _TOPIC_LABEL.get(t, t)
        for t in sorted(probes_df["seed_topic"].unique())
        if t != "general"
        and not probes_df[probes_df["seed_topic"] == t]["brand_mentioned"].any()
    ]
    zero_engines = [e for e in engines if not probes_df[probes_df["engine"] == e]["brand_mentioned"].any()]
    top_displacer = max(comp_disp, key=comp_disp.get) if comp_disp else None

    lines += [
        "",
        "---",
        "",
        "## This Week's Actions",
        "",
    ]
    if zero_engines:
        lines.append(f"- **Zero visibility on {', '.join(e.title() for e in zero_engines)}** — "
                     "Publish on G2, Capterra, and Reddit to seed citations.")
    for zv in zero_vert[:3]:
        lines.append(f"- **No mentions in {zv} vertical** — "
                     f"Create a {zv.lower()} use-case landing page.")
    if top_displacer:
        clean = top_displacer.split(".")[0].title()
        n = comp_disp[top_displacer]
        lines.append(f"- **{clean} displacing you {n}×** — "
                     f"Publish 'Alternatives to {clean}' comparison page and list on G2.")

    # SERP gaps
    if not xref_df.empty:
        critical = xref_df[xref_df["action_priority"] == "critical"]
        if not critical.empty:
            lines += [
                "",
                "---",
                "",
                "## Critical SERP × AI Citation Gaps",
                "",
                "| URL | SERP Weight | AI Engines |",
                "|---|---|---|",
            ]
            for _, r in critical.head(10).iterrows():
                url = r["url"][:70]
                score = r["serp_weighted_score"]
                cited_by = ", ".join(_safe_json_list(r.get("engines_citing_url")))
                lines.append(f"| [{url}]({r['url']}) | {score:.2f} | {cited_by} |")

    lines += ["", "---", "", f"_Report generated by Elmo AEO Monitor · {date.today()}_", ""]
    return "\n".join(lines)


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

    st.markdown(_ambrook_css(), unsafe_allow_html=True)

    run_dates = load_run_dates()
    if not run_dates:
        st.info("No pipeline data yet. Run the pipeline locally to populate the database, then redeploy.")
        st.code("python __main__.py run --skip-trends")
        return

    with st.sidebar:
        st.markdown(f"## AEO Monitor")
        st.caption(f"{COMPANY_NAME} — AI citation & SEO visibility")
        st.divider()

        run_date = st.selectbox(
            "Run date",
            run_dates,
            format_func=lambda d: str(d),
        )

        page = st.radio(
            "View",
            ["Overview", "Placement Targets", "Query Universe", "AE Citations",
             "SERP Analysis", "SEO Ranks", "Weekly Diff", "🔍 Elmo"],
            label_visibility="collapsed",
        )

        st.divider()
        st.caption(f"DB: {DB_PATH.name}")
        conn = get_conn()
        cg_count = conn.execute(
            "SELECT COUNT(*) FROM citation_graph WHERE run_date = ?", [run_date]
        ).fetchone()[0]
        st.caption(f"{cg_count} URLs in citation graph")

        # Weekly report download
        if st.button("⬇ Download weekly report", use_container_width=True):
            report = _generate_weekly_report(run_date)
            st.download_button(
                label="Save report.md",
                data=report,
                file_name=f"elmo_report_{run_date}.md",
                mime="text/markdown",
                use_container_width=True,
            )

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
    elif page == "SEO Ranks":
        page_seo_ranks(run_date)
    elif page == "Weekly Diff":
        page_weekly_diff()
    elif page == "🔍 Elmo":
        page_ai_engine_visibility(run_date)


if __name__ == "__main__":
    main()
