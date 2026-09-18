"""Settings for the templates service (pydantic-settings over .env.local).

DB config is reused from ``neurolegal.core`` (``DATABASE_URL`` + ``NEUROLEGAL_DB_*``);
only S3 and the key prefix are new here. The bucket is shared with the
documents hub and the RAG corpus — template objects live under their own
prefix (``templates/`` by default), and every key is confined to it by
``store.blob.safe_template_key``.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Кап загрузки живёт в contracts (TEMPLATE_MAX_UPLOAD_BYTES), потому что
#: этот же кап применяет RAG-прокси; здесь только размер чанка чтения.
UPLOAD_CHUNK_BYTES = 1024 * 1024


class TemplatesSettings(BaseSettings):
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

    templates_s3_prefix: str = Field("templates/", alias="NEUROLEGAL_TEMPLATES_S3_PREFIX")


settings = TemplatesSettings()
