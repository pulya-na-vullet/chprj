from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Review-pipeline built-in defaults. DEFAULT_REVIEW_MODEL is pinned by the
# T-0042 benchmark (2026-07-18; one synthetic supply contract with 10 planted
# risks, against supply_ru, 12 rules):
#   qwen3.6-flash (baseline, sequential)  809 s, 10 risks
#   openai/gpt-4o-mini, concurrency 4      29-33 s, 9-10 risks  <- chosen
#   gemini-2.0-flash-001, concurrency 4    27 s, 7 risks (-3 high)
#   openai/gpt-4o, concurrency 4           83 s, 8 risks
#   claude-haiku-4.5 / qwen w/o reasoning  >300 s — failed on speed
# 28x speedup, but gpt-4o-mini consistently misses the `acceptance` high risk
# while consistently catching `subject_goods`, which the baseline missed — no
# model beat the baseline on every high risk (LLM runs vary against themselves).
# Client decision 2026-07-18: ship gpt-4o-mini, switchable in the admin console.
DEFAULT_REVIEW_MODEL = "openai/gpt-4o-mini"
DEFAULT_REVIEW_CONCURRENCY = 4


def to_asyncpg_url(url: str) -> str:
    """Normalize a libpq-style postgres URL to an asyncpg-compatible one.

    asyncpg doesn't accept libpq-only query params like `sslmode` or
    `channel_binding`. Strip those, and translate `sslmode=...` to
    `ssl=...` which asyncpg understands.
    """
    asyncpg_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parts = urlsplit(asyncpg_url)
    libpq_only = {"sslmode", "channel_binding"}
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in libpq_only
    ]
    sslmode = next((v for k, v in parse_qsl(parts.query) if k == "sslmode"), None)
    if sslmode:
        kept.append(("ssl", sslmode))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")

    # Embedder selector: "openrouter" (default) | "http://..." (HttpEmbedder URL)
    embedder: str = Field("openrouter", alias="NEUROLEGAL_EMBEDDER")
    embedder_model: str = Field("qwen/qwen3-embedding-8b", alias="NEUROLEGAL_EMBEDDER_MODEL")
    embedder_target_dim: int = Field(1024, alias="NEUROLEGAL_EMBEDDER_TARGET_DIM")

    # LLM model selector for agent
    llm_model: str = Field("qwen/qwen3.6-flash", alias="NEUROLEGAL_LLM_MODEL")

    log_level: str = Field("INFO", alias="NEUROLEGAL_LOG_LEVEL")
    raw_cache_dir: Path = Field(Path("data/raw"), alias="NEUROLEGAL_RAW_CACHE_DIR")

    db_pool_size: int = Field(20, alias="NEUROLEGAL_DB_POOL_SIZE")
    # asyncpg's per-connection prepared-statement cache becomes invalid when
    # transactions land on different backends, which happens with pgbouncer
    # in transaction-pool mode (e.g. Neon's `-pooler.` hostname). Set to 0
    # when going through such a pooler; keep asyncpg's default of 100 for a
    # direct connection to a non-pooled Postgres (the local-docker default).
    db_statement_cache_size: int = Field(100, ge=0, alias="NEUROLEGAL_DB_STATEMENT_CACHE_SIZE")
    embed_batch_size: int = Field(64, alias="NEUROLEGAL_EMBED_BATCH_SIZE")

    # Hybrid-search relevance floor on the per-article RRF score. 0.0 = off
    # (return top-k regardless of how poor the match is). Tune after corpus
    # calibration; raising this above 0 makes off-corpus queries return [].
    rag_min_score: float = Field(0.0, ge=0.0, alias="NEUROLEGAL_RAG_MIN_SCORE")

    # pgvector HNSW search width for hybrid search. The dense leg filters by
    # act AFTER the index scan, so pgvector's default (40) starves filtered
    # searches; 200 keeps recall for per-act filters at current corpus size.
    # Applied per-transaction (SET LOCAL) in store/search.py. Max is
    # pgvector's hard cap.
    hnsw_ef_search: int = Field(200, ge=1, le=1000, alias="NEUROLEGAL_HNSW_EF_SEARCH")

    # Agent → RAG endpoint. Override for staging / docker / split-service deploys.
    rag_base_url: str = Field("http://127.0.0.1:8001", alias="NEUROLEGAL_RAG_BASE_URL")

    documents_base_url: str = Field("http://127.0.0.1:8002", alias="NEUROLEGAL_DOCUMENTS_BASE_URL")

    # RAG → agent endpoint for the operator "users" proxy (/admin/users* on
    # the RAG service forwards to the agent's internal /admin/users*).
    # Override for staging / docker / split-service deploys.
    agent_base_url: str = Field("http://127.0.0.1:8000", alias="NEUROLEGAL_AGENT_BASE_URL")

    # Templates service endpoint — the operator "templates" proxy on the RAG
    # service and (E20) the agent's templates tools both call it over HTTP.
    templates_base_url: str = Field("http://127.0.0.1:8003", alias="NEUROLEGAL_TEMPLATES_BASE_URL")

    # Admin surface (routes + static UI) on the RAG service. No auth — it's
    # a localhost operator tool; flip to false if the RAG service is ever
    # exposed beyond the local machine.
    admin_enabled: bool = Field(True, alias="NEUROLEGAL_ADMIN_ENABLED")

    # Persisted agent settings written by the RAG admin UI and read by the
    # agent at startup. Operator runtime state — gitignored, not committed.
    agent_settings_path: Path = Field(
        Path("data/agent_settings.yaml"), alias="NEUROLEGAL_AGENT_SETTINGS_PATH"
    )

    # S3 для корпусных .docx. Сервис документов держит свои копии этих же полей
    # в DocumentsSettings — дублирование намеренное: rag/ не имеет права
    # импортировать neurolegal.documents.*.
    s3_endpoint: str | None = Field(None, alias="NEUROLEGAL_S3_ENDPOINT")
    s3_bucket: str = Field("nfs-neurolegal-documents", alias="NEUROLEGAL_S3_BUCKET")
    s3_region: str = Field("us-east-1", alias="NEUROLEGAL_S3_REGION")
    s3_access_key: str | None = Field(None, alias="NEUROLEGAL_S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(None, alias="NEUROLEGAL_S3_SECRET_KEY")
    corpus_s3_prefix: str = Field("corpus/", alias="NEUROLEGAL_CORPUS_S3_PREFIX")

    # Tavily API key for the web-search tool. Optional — if absent, the tool
    # will not be registered.
    tavily_api_key: str | None = Field(None, alias="NEUROLEGAL_TAVILY_API_KEY")

    # Outbound mail config — DORMANT since T-0026 (2026-07-11): the auth mail
    # flows (email verification / password-reset links) were removed, so
    # nothing sends mail at runtime. Kept for when mail returns. No
    # NEUROLEGAL_SMTP_HOST → console mode (mail goes to the log); NEUROLEGAL_SMTP_FROM is
    # required once HOST is set.
    smtp_host: str | None = Field(None, alias="NEUROLEGAL_SMTP_HOST")
    smtp_port: int = Field(587, alias="NEUROLEGAL_SMTP_PORT")
    smtp_user: str | None = Field(None, alias="NEUROLEGAL_SMTP_USER")
    smtp_password: str | None = Field(None, alias="NEUROLEGAL_SMTP_PASSWORD")
    smtp_from: str | None = Field(None, alias="NEUROLEGAL_SMTP_FROM")
    smtp_starttls: bool = Field(True, alias="NEUROLEGAL_SMTP_STARTTLS")

    # Browser-facing origin of the agent service. The Origin middleware in
    # `agent/api/app.py` validates mutating requests against it (CSRF guard).
    # Must be the real browser-facing origin in prod. (Historically also built
    # email links; that flow is gone since T-0026.)
    public_base_url: str = Field("http://127.0.0.1:8000", alias="NEUROLEGAL_PUBLIC_BASE_URL")

    # Secure flag on the `neurolegal_session` cookie. False for local http dev;
    # must be true wherever the agent is served over https.
    cookie_secure: bool = Field(False, alias="NEUROLEGAL_COOKIE_SECURE")

    # Directory holding contract-review playbooks (risk checklists per doc type).
    playbooks_dir: Path = Field(Path("playbooks"), alias="NEUROLEGAL_PLAYBOOKS_DIR")

    # LLM model override for the contract-review pipeline. None = reuse
    # `llm_model` (the agent's default chat model).
    review_model: str | None = Field(None, alias="NEUROLEGAL_REVIEW_MODEL")

    # Parallel rule-assessment width for the review pipeline. None = not set
    # (admin setting or DEFAULT_REVIEW_CONCURRENCY applies, see agent deps).
    # ge=1: a Semaphore(0) in ReviewEngine deadlocks every worker forever.
    # le=12: mirrors contracts.agent_settings.ReviewSettings.concurrency.
    review_concurrency: int | None = Field(None, alias="NEUROLEGAL_REVIEW_CONCURRENCY", ge=1, le=12)

    # Shared secret between the agent and the documents hub. When set, the
    # agent sends it as `X-Internal-Token` on every hub request and the hub
    # rejects requests whose header doesn't match (constant-time compare).
    internal_token: str | None = Field(None, alias="NEUROLEGAL_INTERNAL_TOKEN")
    # Fail-fast switch for the hub: if true and internal_token is unset, the
    # hub refuses to start (mirrors the tessdata preflight check). Default
    # false so local dev works without the secret configured.
    require_internal_token: bool = Field(False, alias="NEUROLEGAL_REQUIRE_INTERNAL_TOKEN")


settings = Settings()
