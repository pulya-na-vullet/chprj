"""Settings for the documents hub service (pydantic-settings over .env.local).

DB config is reused from ``neurolegal.core`` (``DATABASE_URL`` + ``NEUROLEGAL_DB_*``);
only S3, OCR-data, and the service base URL are new here.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_SUFFIXES = frozenset({".docx", ".pdf"})


class DocumentsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    s3_endpoint: str | None = Field(None, alias="NEUROLEGAL_S3_ENDPOINT")
    s3_bucket: str = Field("nfs-neurolegal-documents", alias="NEUROLEGAL_S3_BUCKET")
    s3_region: str = Field("us-east-1", alias="NEUROLEGAL_S3_REGION")
    s3_access_key: str | None = Field(None, alias="NEUROLEGAL_S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(None, alias="NEUROLEGAL_S3_SECRET_KEY")

    tessdata_path: Path = Field(Path("data/tessdata"), alias="NEUROLEGAL_TESSDATA_PATH")

    documents_base_url: str = Field("http://127.0.0.1:8002", alias="NEUROLEGAL_DOCUMENTS_BASE_URL")

    # T-0017: «Суть» — LLM-выжимка. Тот же OPENROUTER_API_KEY, как в agent/rag;
    # без ключа → выжимка и sweep молча выключены.
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")
    summary_model: str = Field("openai/gpt-4o-mini", alias="NEUROLEGAL_SUMMARY_MODEL")

    @property
    def max_upload_bytes(self) -> int:
        return MAX_UPLOAD_BYTES

    @property
    def allowed_suffixes(self) -> frozenset[str]:
        return ALLOWED_SUFFIXES


settings = DocumentsSettings()
