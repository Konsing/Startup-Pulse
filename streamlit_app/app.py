"""Startup Pulse Dashboard — Streamlit application.

Visualizes skill trends, market metrics, and recent job postings
from the BigQuery data warehouse.
"""

import streamlit as st

st.set_page_config(page_title="Startup Pulse", layout="wide")

import plotly.express as px

from utils.bq_client import get_dataset, query_df

# ── Custom CSS ─────────────────────────────────────────────────────────

st.markdown("""
<style>
/* --- Metric cards: glass-morphism --- */
[data-testid="stMetric"] {
    background: rgba(108, 99, 255, 0.08);
    border: 1px solid rgba(108, 99, 255, 0.20);
    border-radius: 12px;
    padding: 16px 20px;
}
[data-testid="stMetricLabel"] {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.7;
}
[data-testid="stMetricValue"] {
    font-size: 1.8rem;
    font-weight: 700;
}

/* --- Sidebar accent --- */
[data-testid="stSidebar"] > div:first-child {
    border-top: 3px solid #6C63FF;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 0.95rem;
    padding: 4px 0;
}

/* --- Page titles --- */
h1 {
    letter-spacing: -0.02em;
    font-weight: 800 !important;
}

/* --- Subheaders: accent underline --- */
[data-testid="stSubheader"]  {
    border-bottom: 2px solid rgba(108, 99, 255, 0.35);
    padding-bottom: 6px;
    margin-bottom: 12px;
}

/* --- Dataframe containers --- */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
}

/* --- Muted dividers --- */
hr {
    border-color: rgba(250, 250, 250, 0.08) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Plotly chart theme ─────────────────────────────────────────────────

CHART_THEME = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", size=13, color="#FAFAFA"),
    colorway=[
        "#6C63FF", "#3DD9D6", "#FF6B6B", "#FFD93D",
        "#A78BFA", "#34D399", "#F472B6", "#60A5FA",
    ],
    margin=dict(l=20, r=20, t=50, b=20),
    hoverlabel=dict(bgcolor="#1A1D29", font_size=13, font_color="#FAFAFA"),
)

DATASET = get_dataset()


# ── Data loaders (cached) ─────────────────────────────────────────────


@st.cache_data(ttl=300)
def load_skill_trends():
    return query_df(f"""
        SELECT skill, category,
               MAX(frequency) AS frequency,
               MAX(tfidf_score) AS tfidf_score,
               MAX(avg_salary) AS avg_salary,
               MAX(num_jobs) AS num_jobs,
               MAX(collected_at) AS collected_at
        FROM `{DATASET}.skill_trends`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        GROUP BY skill, category
        ORDER BY frequency DESC
    """)


@st.cache_data(ttl=300)
def load_market_metrics():
    return query_df(f"""
        SELECT source, role_category, total_jobs,
               avg_salary, median_salary, remote_pct,
               top_skills, collected_at
        FROM `{DATASET}.market_metrics`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY collected_at DESC
    """)


@st.cache_data(ttl=300)
def load_recent_jobs():
    return query_df(f"""
        SELECT job_id, source, company, title, salary_min, salary_max,
               location, remote, company_stage, yc_batch, url,
               MAX(collected_at) AS collected_at
        FROM `{DATASET}.raw_jobs`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        GROUP BY job_id, source, company, title, salary_min, salary_max,
                 location, remote, company_stage, yc_batch, url
        ORDER BY collected_at DESC
    """)


# ── Sidebar ───────────────────────────────────────────────────────────

st.sidebar.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <rect width="32" height="32" rx="8" fill="#6C63FF" fill-opacity="0.15"/>
        <polyline points="4,18 10,18 13,8 16,24 19,14 22,18 28,18"
                  stroke="#6C63FF" stroke-width="2.4" stroke-linecap="round"
                  stroke-linejoin="round" fill="none"/>
    </svg>
    <span style="font-size:1.45rem;font-weight:800;letter-spacing:-0.02em;">
        Startup Pulse
    </span>
</div>
<span style="font-size:0.82rem;opacity:0.55;letter-spacing:0.03em;">
    Startup Job Market Intelligence
</span>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Skill Trends", "Market Metrics", "Job Explorer"],
)

# ── Overview page ─────────────────────────────────────────────────────

if page == "Overview":
    st.title("Startup Pulse Overview")

    try:
        skills_df = load_skill_trends()
        jobs_df = load_recent_jobs()
        metrics_df = load_market_metrics()
    except Exception as e:
        st.error(f"Could not load data from BigQuery: {e}")
        st.info("Make sure the ETL pipeline has run at least once.")
        st.stop()

    if jobs_df.empty:
        st.warning("No data available yet. Run the ETL pipeline first.")
        st.stop()

    if "collected_at" in jobs_df.columns and not jobs_df["collected_at"].isna().all():
        latest_ts = jobs_df["collected_at"].max()
        st.caption(f"Last refreshed: {latest_ts:%Y-%m-%d %H:%M} UTC")

    # Build per-source stats: job counts from raw_jobs, salary from market_metrics
    source_stats = jobs_df.groupby("source").agg(
        total_jobs=("job_id", "count"),
        remote_pct=("remote", lambda x: round(x.sum() / len(x) * 100) if len(x) > 0 else 0),
    ).reset_index()

    # Use market_metrics for avg_salary (computed fresh each pipeline run,
    # not affected by cross-run deduplication in raw_jobs)
    if not metrics_df.empty:
        latest_metrics = metrics_df.sort_values("collected_at").groupby("source").last().reset_index()
        source_stats = source_stats.merge(
            latest_metrics[["source", "avg_salary"]],
            on="source",
            how="left",
        )
    else:
        source_stats["avg_salary"] = None

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Jobs", len(jobs_df))
    col2.metric("Sources", len(source_stats))
    col3.metric("Unique Skills", len(skills_df["skill"].unique()) if not skills_df.empty else 0)
    col4.metric("Avg Remote %", f"{source_stats['remote_pct'].mean():.0f}%")

    st.divider()

    # Two-column layout: top skills + top sources
    left, right = st.columns(2)

    with left:
        st.subheader("Top Skills (by Frequency)")
        if not skills_df.empty:
            top_skills = skills_df.nlargest(15, "frequency")[
                ["skill", "category", "frequency", "avg_salary"]
            ]
            st.dataframe(top_skills, use_container_width=True, hide_index=True)
        else:
            st.info("No skill data yet.")

    with right:
        st.subheader("Sources Overview")
        st.dataframe(
            source_stats[["source", "total_jobs", "avg_salary", "remote_pct"]],
            use_container_width=True,
            hide_index=True,
        )

    # Recent jobs preview
    if not jobs_df.empty:
        st.subheader("Latest Job Postings")
        st.dataframe(
            jobs_df[["company", "title", "source", "location", "salary_min", "salary_max"]].head(10),
            use_container_width=True,
            hide_index=True,
        )

# ── Skill Trends page ────────────────────────────────────────────────

elif page == "Skill Trends":
    st.title("Skill Trends")

    try:
        skills_df = load_skill_trends()
    except Exception as e:
        st.error(f"Could not load skill data: {e}")
        st.stop()

    if skills_df.empty:
        st.warning("No skill data available.")
        st.stop()

    # Category filter
    categories = ["All"] + sorted(skills_df["category"].unique().tolist())
    selected_cat = st.selectbox("Filter by category", categories)

    filtered = skills_df
    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]

    top_n = st.slider("Number of skills to show", 10, 50, 20)
    chart_data = filtered.nlargest(top_n, "frequency")

    fig = px.bar(
        chart_data,
        x="frequency",
        y="skill",
        color="category",
        orientation="h",
        title=f"Top {top_n} Skills by Frequency",
        labels={"frequency": "Job Count", "skill": "Skill"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 25), **CHART_THEME)
    st.plotly_chart(fig, use_container_width=True)

    # Salary by skill
    salary_data = filtered.dropna(subset=["avg_salary"]).nlargest(top_n, "avg_salary")
    if not salary_data.empty:
        fig_salary = px.bar(
            salary_data,
            x="avg_salary",
            y="skill",
            color="category",
            orientation="h",
            title="Top Skills by Average Salary",
            labels={"avg_salary": "Average Salary ($)", "skill": "Skill"},
        )
        fig_salary.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 25), **CHART_THEME)
        st.plotly_chart(fig_salary, use_container_width=True)

    # Detailed table
    st.subheader("Skill Details")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

# ── Market Metrics page ──────────────────────────────────────────────

elif page == "Market Metrics":
    st.title("Market Metrics")

    try:
        jobs_df = load_recent_jobs()
        metrics_df = load_market_metrics()
    except Exception as e:
        st.error(f"Could not load metrics: {e}")
        st.stop()

    if jobs_df.empty:
        st.warning("No metrics available.")
        st.stop()

    # Compute per-source stats: counts from raw_jobs, salary from market_metrics
    source_stats = jobs_df.groupby("source").agg(
        total_jobs=("job_id", "count"),
        remote_pct=("remote", lambda x: round(x.sum() / len(x) * 100) if len(x) > 0 else 0),
    ).reset_index()

    # Jobs by source
    fig_source = px.bar(
        source_stats,
        x="source",
        y="total_jobs",
        color="source",
        title="Jobs by Source",
        labels={"total_jobs": "Total Jobs"},
    )
    fig_source.update_layout(**CHART_THEME)
    st.plotly_chart(fig_source, use_container_width=True)

    # Remote percentage by source
    fig_remote = px.bar(
        source_stats,
        x="source",
        y="remote_pct",
        color="source",
        title="Remote Job Percentage by Source",
        labels={"remote_pct": "Remote %"},
    )
    fig_remote.update_layout(**CHART_THEME)
    st.plotly_chart(fig_remote, use_container_width=True)

    # Salary by source from market_metrics (always fresh)
    if not metrics_df.empty:
        latest_metrics = metrics_df.sort_values("collected_at").groupby("source").last().reset_index()
        salary_metrics = latest_metrics.dropna(subset=["avg_salary"])
        if not salary_metrics.empty:
            fig_salary_bar = px.bar(
                salary_metrics,
                x="source",
                y=["avg_salary", "median_salary"],
                barmode="group",
                title="Salary by Source (Avg & Median)",
                labels={"value": "Salary ($)", "variable": "Metric"},
            )
            fig_salary_bar.update_layout(**CHART_THEME)
            st.plotly_chart(fig_salary_bar, use_container_width=True)

    # Salary distribution box plot from per-job data (when available)
    if not jobs_df.empty:
        salary_jobs = jobs_df.dropna(subset=["salary_min", "salary_max"])
        if not salary_jobs.empty:
            salary_jobs = salary_jobs.copy()
            salary_jobs["avg_salary"] = (salary_jobs["salary_min"] + salary_jobs["salary_max"]) / 2

            fig_salary = px.box(
                salary_jobs,
                x="source",
                y="avg_salary",
                color="source",
                title="Salary Distribution by Source",
                labels={"avg_salary": "Average Salary ($)"},
            )
            fig_salary.update_layout(**CHART_THEME)
            st.plotly_chart(fig_salary, use_container_width=True)

    # Company stage breakdown
    if not jobs_df.empty and "company_stage" in jobs_df.columns:
        stage_data = jobs_df.dropna(subset=["company_stage"])
        if not stage_data.empty:
            stage_counts = stage_data["company_stage"].value_counts().reset_index()
            stage_counts.columns = ["company_stage", "count"]
            fig_stage = px.pie(
                stage_counts,
                values="count",
                names="company_stage",
                title="Jobs by Company Stage",
                hole=0.4,
            )
            fig_stage.update_layout(**CHART_THEME)
            st.plotly_chart(fig_stage, use_container_width=True)

    # Full metrics table from market_metrics (includes fresh avg_salary)
    st.subheader("All Market Metrics")
    if not metrics_df.empty:
        latest_metrics = metrics_df.sort_values("collected_at").groupby("source").last().reset_index()
        display_metrics = source_stats.merge(
            latest_metrics[["source", "avg_salary", "median_salary"]],
            on="source",
            how="left",
        )
        st.dataframe(display_metrics, use_container_width=True, hide_index=True)
    else:
        st.dataframe(source_stats, use_container_width=True, hide_index=True)

# ── Job Explorer page ────────────────────────────────────────────────

elif page == "Job Explorer":
    st.title("Job Explorer")

    try:
        jobs_df = load_recent_jobs()
    except Exception as e:
        st.error(f"Could not load jobs: {e}")
        st.stop()

    if jobs_df.empty:
        st.warning("No jobs available.")
        st.stop()

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        sources = ["All"] + sorted(jobs_df["source"].unique().tolist())
        selected_source = st.selectbox("Source", sources)
    with col2:
        remote_filter = st.selectbox("Remote", ["All", "Remote", "On-site"])
    with col3:
        search = st.text_input("Search (company or title)")

    filtered = jobs_df
    if selected_source != "All":
        filtered = filtered[filtered["source"] == selected_source]
    if remote_filter == "Remote":
        filtered = filtered[filtered["remote"] == True]
    elif remote_filter == "On-site":
        filtered = filtered[filtered["remote"] == False]
    if search:
        mask = (
            filtered["company"].str.contains(search, case=False, na=False)
            | filtered["title"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    st.markdown(
        f'<span style="display:inline-block;background:rgba(108,99,255,0.15);'
        f'color:#FAFAFA;padding:4px 14px;border-radius:20px;font-size:0.88rem;'
        f'font-weight:600;letter-spacing:0.02em;margin-bottom:8px;">'
        f'Showing {len(filtered)} jobs</span>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        filtered[["company", "title", "source", "location", "remote",
                  "salary_min", "salary_max", "company_stage", "yc_batch", "collected_at"]],
        use_container_width=True,
        hide_index=True,
    )
