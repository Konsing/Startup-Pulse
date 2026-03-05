"""Reddit Trends Dashboard — Streamlit application.

Visualizes keyword trends, subreddit engagement metrics, and recent
posts from the BigQuery data warehouse.
"""

import streamlit as st

st.set_page_config(page_title="Reddit Trends", layout="wide")

from utils.bq_client import get_dataset, query_df

DATASET = get_dataset()


# ── Data loaders (cached) ─────────────────────────────────────────────


@st.cache_data(ttl=300)
def load_keyword_trends():
    return query_df(f"""
        SELECT keyword, subreddit, category, frequency, tfidf_score,
               avg_score, avg_comments, collected_at
        FROM `{DATASET}.keyword_trends`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY tfidf_score DESC
    """)


@st.cache_data(ttl=300)
def load_subreddit_metrics():
    return query_df(f"""
        SELECT subreddit, category, total_posts_collected,
               avg_score, median_score, max_score,
               avg_comments, total_comments, avg_upvote_ratio,
               posting_rate_per_hour, collected_at
        FROM `{DATASET}.subreddit_metrics`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY collected_at DESC
    """)


@st.cache_data(ttl=300)
def load_recent_posts(limit=200):
    return query_df(f"""
        SELECT post_id, subreddit, category, title, score,
               num_comments, upvote_ratio, created_utc, collected_at,
               listing_type
        FROM `{DATASET}.raw_posts`
        ORDER BY collected_at DESC
        LIMIT {limit}
    """)


# ── Sidebar ───────────────────────────────────────────────────────────

st.sidebar.title("Reddit Trends")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Keyword Trends", "Subreddit Metrics", "Recent Posts"],
)

# ── Overview page ─────────────────────────────────────────────────────

if page == "Overview":
    st.title("Reddit Trends Overview")

    try:
        metrics_df = load_subreddit_metrics()
        keywords_df = load_keyword_trends()
        posts_df = load_recent_posts(limit=50)
    except Exception as e:
        st.error(f"Could not load data from BigQuery: {e}")
        st.info("Make sure the ETL pipeline has run at least once.")
        st.stop()

    if metrics_df.empty:
        st.warning("No data available yet. Run the ETL pipeline first.")
        st.stop()

    # KPI cards
    latest = metrics_df.sort_values("collected_at", ascending=False).drop_duplicates("subreddit")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Subreddits Tracked", len(latest))
    col2.metric("Total Posts", int(latest["total_posts_collected"].sum()))
    col3.metric("Avg Score", f"{latest['avg_score'].mean():.0f}")
    col4.metric("Unique Keywords", len(keywords_df["keyword"].unique()) if not keywords_df.empty else 0)

    st.divider()

    # Two-column layout: top keywords + top subreddits
    left, right = st.columns(2)

    with left:
        st.subheader("Top Keywords (by TF-IDF)")
        if not keywords_df.empty:
            top_kw = keywords_df.nlargest(15, "tfidf_score")[
                ["keyword", "subreddit", "tfidf_score", "frequency"]
            ]
            st.dataframe(top_kw, use_container_width=True, hide_index=True)
        else:
            st.info("No keyword data yet.")

    with right:
        st.subheader("Top Subreddits (by Avg Score)")
        if not latest.empty:
            top_subs = latest.nlargest(10, "avg_score")[
                ["subreddit", "category", "avg_score", "total_posts_collected"]
            ]
            st.dataframe(top_subs, use_container_width=True, hide_index=True)

# ── Keyword Trends page ──────────────────────────────────────────────

elif page == "Keyword Trends":
    st.title("Keyword Trends")

    try:
        keywords_df = load_keyword_trends()
    except Exception as e:
        st.error(f"Could not load keyword data: {e}")
        st.stop()

    if keywords_df.empty:
        st.warning("No keyword data available.")
        st.stop()

    # Category filter
    categories = ["All"] + sorted(keywords_df["category"].unique().tolist())
    selected_cat = st.selectbox("Filter by category", categories)

    filtered = keywords_df
    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]

    # Bar chart: top keywords by TF-IDF
    import plotly.express as px

    top_n = st.slider("Number of keywords to show", 10, 50, 20)
    chart_data = filtered.nlargest(top_n, "tfidf_score")

    fig = px.bar(
        chart_data,
        x="tfidf_score",
        y="keyword",
        color="subreddit",
        orientation="h",
        title=f"Top {top_n} Keywords by TF-IDF Score",
        labels={"tfidf_score": "TF-IDF Score", "keyword": "Keyword"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 25))
    st.plotly_chart(fig, use_container_width=True)

    # Word cloud
    st.subheader("Word Cloud")
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt

    word_freq = dict(zip(filtered["keyword"], filtered["tfidf_score"]))
    if word_freq:
        wc = WordCloud(width=800, height=400, background_color="white").generate_from_frequencies(word_freq)
        fig_wc, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        st.pyplot(fig_wc)

    # Detailed table
    st.subheader("Keyword Details")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

# ── Subreddit Metrics page ───────────────────────────────────────────

elif page == "Subreddit Metrics":
    st.title("Subreddit Engagement Metrics")

    try:
        metrics_df = load_subreddit_metrics()
    except Exception as e:
        st.error(f"Could not load metrics: {e}")
        st.stop()

    if metrics_df.empty:
        st.warning("No metrics available.")
        st.stop()

    import plotly.express as px

    # Latest snapshot per subreddit
    latest = metrics_df.sort_values("collected_at", ascending=False).drop_duplicates("subreddit")

    # Grouped bar chart: avg score by subreddit
    fig_score = px.bar(
        latest.sort_values("avg_score", ascending=False),
        x="subreddit",
        y="avg_score",
        color="category",
        title="Average Post Score by Subreddit",
        labels={"avg_score": "Average Score"},
    )
    st.plotly_chart(fig_score, use_container_width=True)

    # Scatter: avg score vs avg comments
    fig_scatter = px.scatter(
        latest,
        x="avg_score",
        y="avg_comments",
        size="total_posts_collected",
        color="category",
        hover_name="subreddit",
        title="Engagement: Score vs Comments",
        labels={"avg_score": "Average Score", "avg_comments": "Average Comments"},
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Metrics over time (if multiple collection runs)
    if len(metrics_df) > len(latest):
        st.subheader("Metrics Over Time")
        selected_sub = st.selectbox("Select subreddit", sorted(metrics_df["subreddit"].unique()))
        sub_data = metrics_df[metrics_df["subreddit"] == selected_sub].sort_values("collected_at")

        fig_time = px.line(
            sub_data,
            x="collected_at",
            y=["avg_score", "avg_comments"],
            title=f"r/{selected_sub} — Score & Comments Over Time",
            labels={"collected_at": "Collection Time", "value": "Value"},
        )
        st.plotly_chart(fig_time, use_container_width=True)

    # Full metrics table
    st.subheader("All Subreddit Metrics")
    st.dataframe(latest, use_container_width=True, hide_index=True)

# ── Recent Posts page ────────────────────────────────────────────────

elif page == "Recent Posts":
    st.title("Recent Posts")

    try:
        posts_df = load_recent_posts()
    except Exception as e:
        st.error(f"Could not load posts: {e}")
        st.stop()

    if posts_df.empty:
        st.warning("No posts available.")
        st.stop()

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        categories = ["All"] + sorted(posts_df["category"].unique().tolist())
        selected_cat = st.selectbox("Category", categories)
    with col2:
        subreddits = ["All"] + sorted(posts_df["subreddit"].unique().tolist())
        selected_sub = st.selectbox("Subreddit", subreddits)

    filtered = posts_df
    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]
    if selected_sub != "All":
        filtered = filtered[filtered["subreddit"] == selected_sub]

    st.write(f"Showing {len(filtered)} posts")
    st.dataframe(
        filtered[["title", "subreddit", "category", "score", "num_comments", "upvote_ratio", "listing_type", "created_utc"]],
        use_container_width=True,
        hide_index=True,
    )
