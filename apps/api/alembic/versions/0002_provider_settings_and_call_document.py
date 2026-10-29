"""Add encrypted provider settings and document-level call history."""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid, inspect, func

revision = "0002_provider_settings_and_call_document"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "provider_settings" not in tables:
        op.create_table(
            "provider_settings",
            Column("tenant_id", Uuid(), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
            Column("endpoint", String(500), nullable=False, server_default="https://api.openai.com/v1"),
            Column("encrypted_api_key", Text(), nullable=True),
            Column("model", String(120), nullable=False, server_default="gpt-4o-mini"),
            Column("mode", String(20), nullable=False, server_default="mock"),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
            Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )
    call_columns = {column["name"] for column in inspector.get_columns("api_calls")}
    if "document_id" not in call_columns:
        op.add_column(
            "api_calls",
            Column("document_id", Uuid(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_api_calls_document_id", "api_calls", ["document_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    call_columns = {column["name"] for column in inspector.get_columns("api_calls")}
    if "document_id" in call_columns:
        op.drop_index("ix_api_calls_document_id", table_name="api_calls")
        op.drop_column("api_calls", "document_id")
    if "provider_settings" in set(inspector.get_table_names()):
        op.drop_table("provider_settings")
