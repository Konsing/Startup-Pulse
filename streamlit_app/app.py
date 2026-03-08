"""Startup Pulse Dashboard — Streamlit application.

Visualizes skill trends, market metrics, and recent job postings
from the BigQuery data warehouse.
"""

import streamlit as st

st.set_page_config(page_title="Startup Pulse", layout="wide")

from utils.bq_client import get_dataset, query_df

DATASET = get_dataset()


# ── Data loaders (cached) ─────────────────────────────────────────────


@st.cache_data(ttl=300)
def load_skill_trends():
    return query_df(f"""
        SELECT skill, category, frequency, tfidf_score,
               avg_salary, num_jobs, collected_at
        FROM `{DATASET}.skill_trends`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
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

st.sidebar.title("Startup Pulse")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Skill Trends", "Market Metrics", "Job Explorer"],
)

# ── Overview page ─────────────────────────────────────────────────────

if page == "Overview":
    st.title("Startup Pulse Overview")

    try:
        metrics_df = load_market_metrics()
        skills_df = load_skill_trends()
        jobs_df = load_recent_jobs()
    except Exception as e:
        st.error(f"Could not load data from BigQuery: {e}")
        st.info("Make sure the ETL pipeline has run at least once.")
        st.stop()

    if metrics_df.empty:
        st.warning("No data available yet. Run the ETL pipeline first.")
        st.stop()

    # KPI cards
    latest = metrics_df.sort_values("collected_at", ascending=False).drop_duplicates("source")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Jobs", int(latest["total_jobs"].sum()))
    col2.metric("Sources", len(latest))
    col3.metric("Unique Skills", len(skills_df["skill"].unique()) if not skills_df.empty else 0)
    col4.metric("Avg Remote %", f"{latest['remote_pct'].mean():.0f}%")

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
        if not latest.empty:
            st.dataframe(
                latest[["source", "total_jobs", "avg_salary", "remote_pct"]],
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

    # Bar chart: top skills by frequency
    import plotly.express as px

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
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 25))
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
        fig_salary.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 25))
        st.plotly_chart(fig_salary, use_container_width=True)

    # Detailed table
    st.subheader("Skill Details")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

# ── Market Metrics page ──────────────────────────────────────────────

elif page == "Market Metrics":
    st.title("Market Metrics")

    try:
        metrics_df = load_market_metrics()
        jobs_df = load_recent_jobs()
    except Exception as e:
        st.error(f"Could not load metrics: {e}")
        st.stop()

    if metrics_df.empty:
        st.warning("No metrics available.")
        st.stop()

    import plotly.express as px

    latest = metrics_df.sort_values("collected_at", ascending=False).drop_duplicates("source")

    # Jobs by source
    fig_source = px.bar(
        latest,
        x="source",
        y="total_jobs",
        color="source",
        title="Jobs by Source",
        labels={"total_jobs": "Total Jobs"},
    )
    st.plotly_chart(fig_source, use_container_width=True)

    # Remote percentage by source
    fig_remote = px.bar(
        latest,
        x="source",
        y="remote_pct",
        color="source",
        title="Remote Job Percentage by Source",
        labels={"remote_pct": "Remote %"},
    )
    st.plotly_chart(fig_remote, use_container_width=True)

    # Salary distributions (if job data available)
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
            )
            st.plotly_chart(fig_stage, use_container_width=True)

    # Full metrics table
    st.subheader("All Market Metrics")
    st.dataframe(latest, use_container_width=True, hide_index=True)

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

    st.write(f"Showing {len(filtered)} jobs")
    st.dataframe(
        filtered[["company", "title", "source", "location", "remote",
                  "salary_min", "salary_max", "company_stage", "yc_batch", "collected_at"]],
        use_container_width=True,
        hide_index=True,
    )
