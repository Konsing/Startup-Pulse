"""Centralized configuration for the Startup Pulse pipeline."""

# -- Data source URLs --------------------------------------------------------
YC_JOBS_BASE_URL = "https://www.workatastartup.com/jobs/l"
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"

# -- YC role categories (each is a separate page on workatastartup.com) ------
YC_CATEGORY_SLUGS = [
    "software-engineer",
    "designer",
    "recruiting",
    "science",
    "product-manager",
    "operations",
    "sales-manager",
    "marketing",
    "legal",
    "finance",
]

# -- Greenhouse board tokens -------------------------------------------------
# Each token maps to a company's public job board on Greenhouse.
# API: GET {GREENHOUSE_API_BASE}/{token}/jobs?content=true
GREENHOUSE_BOARD_TOKENS = [
    "airbnb",
    "airtable",
    "brex",
    "cloudflare",
    "cockroachlabs",
    "coinbase",
    "databricks",
    "datadog",
    "discord",
    "doordashusa",
    "elastic",
    "figma",
    "gitlab",
    "gusto",
    "instacart",
    "netlify",
    "pagerduty",
    "reddit",
    "scaleai",
    "stripe",
    "twilio",
    "vercel",
]

# -- Scraping settings -------------------------------------------------------
SCRAPE_TIMEOUT_MS = 60_000          # Playwright page timeout
SCRAPE_DELAY_SECONDS = 2            # Polite delay between page loads

# -- NLP settings ------------------------------------------------------------
TFIDF_MAX_FEATURES = 300
TFIDF_NGRAM_RANGE = (1, 2)
TFIDF_MIN_DF = 2
TFIDF_MAX_DF = 0.85
MAX_SKILLS_PER_CATEGORY = 50

# -- Skill taxonomy ----------------------------------------------------------
# Curated list of tech skills to match in job descriptions.
# Grouped by category for dashboard filtering.
SKILL_TAXONOMY = {
    "languages": [
        "python", "javascript", "typescript", "java", "go", "rust", "ruby",
        "c++", "c#", "swift", "kotlin", "scala", "php", "sql", "r",
    ],
    "frameworks": [
        "react", "next.js", "vue", "angular", "django", "flask", "fastapi",
        "spring", "rails", "express", "node.js", "svelte", "remix",
    ],
    "infra_and_cloud": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "ansible", "jenkins", "github actions", "circleci", "datadog",
    ],
    "data_and_ml": [
        "pytorch", "tensorflow", "pandas", "spark", "airflow", "dbt",
        "snowflake", "bigquery", "redshift", "kafka", "redis", "postgresql",
        "mongodb", "elasticsearch", "llm", "rag", "langchain", "openai",
    ],
}

# -- Role categories ---------------------------------------------------------
ROLE_CATEGORIES = {
    "backend": ["backend", "server", "api", "microservice", "systems"],
    "frontend": ["frontend", "front-end", "ui", "ux", "web"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "ml_ai": ["machine learning", "ml ", "ai ", "data scientist", "deep learning",
              "nlp", "computer vision", "llm"],
    "data_eng": ["data engineer", "analytics engineer", "etl", "data platform",
                 "data infrastructure"],
    "devops_sre": ["devops", "sre", "infrastructure", "platform engineer",
                   "reliability", "cloud engineer"],
    "mobile": ["ios", "android", "mobile", "react native", "flutter"],
}

# -- Seniority levels --------------------------------------------------------
SENIORITY_KEYWORDS = {
    "intern": ["intern", "internship"],
    "junior": ["junior", "jr.", "entry level", "new grad", "associate"],
    "mid": ["mid-level", "mid level", "intermediate"],
    "senior": ["senior", "sr.", "experienced"],
    "staff": ["staff", "principal", "distinguished"],
    "lead": ["lead", "tech lead", "team lead", "engineering manager"],
    "director": ["director", "vp", "head of"],
}

# -- BigQuery settings -------------------------------------------------------
BQ_LOCATION = "US"
