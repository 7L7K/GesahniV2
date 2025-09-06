"""bootstrap: schemas, extensions, and core tables

Revision ID: 0001_bootstrap
Revises: 
Create Date: 2025-09-06 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extensions & Schemas ---
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    for schema in ("auth", "users", "care", "music", "tokens", "audit"):
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')

    # ===========================
    # AUTH
    # ===========================
    op.create_table(
        "users",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text()),
        sa.Column("name", sa.String(length=200)),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("auth_providers", sa.Text()),
        schema="auth",
    )

    op.create_table(
        "devices",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_name", sa.String(length=200)),
        sa.Column("ua_hash", sa.String(length=128), nullable=False),
        sa.Column("ip_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        schema="auth",
    )

    op.create_table(
        "sessions",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("mfa_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="auth",
    )

    op.create_table(
        "auth_identities",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_iss", sa.String(length=255)),
        sa.Column("provider_sub", sa.String(length=255)),
        sa.Column("email_normalized", sa.String(length=320)),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_iss", "provider_sub", name="uq_auth_identity_provider_tuple"),
        schema="auth",
    )

    op.create_table(
        "pat_tokens",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("exp_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        schema="auth",
    )

    # ===========================
    # USERS
    # ===========================
    op.create_table(
        "user_stats",
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("login_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_login", sa.DateTime(timezone=True)),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="users",
    )

    # ===========================
    # CARE
    # ===========================
    op.create_table(
        "residents",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(length=200)),
        schema="care",
    )
    op.create_table(
        "caregivers",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(length=200)),
        sa.Column("phone", sa.String(length=50)),
        schema="care",
    )
    op.create_table(
        "caregiver_resident",
        sa.Column("caregiver_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.caregivers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("primary_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("caregiver_id", "resident_id", name="pk_caregiver_resident"),
        schema="care",
    )
    op.create_table(
        "devices",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="SET NULL")),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("battery_pct", sa.Integer()),
        sa.Column("battery_low_since", sa.DateTime(timezone=True)),
        sa.Column("battery_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("offline_since", sa.DateTime(timezone=True)),
        sa.Column("offline_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="care",
    )
    op.create_table(
        "alerts",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(length=50)),
        sa.Column("severity", sa.String(length=20)),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=30)),
        sa.Column("ack_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        schema="care",
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True)),
        sa.Column("type", sa.String(length=50)),
        sa.Column("meta", psql.JSONB()),
        schema="care",
    )
    op.create_table(
        "care_sessions",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(length=200)),
        sa.Column("transcript_uri", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="care",
    )
    op.create_table(
        "contacts",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200)),
        sa.Column("phone", sa.String(length=50)),
        sa.Column("priority", sa.Integer()),
        sa.Column("quiet_hours", sa.String(length=50)),
        schema="care",
    )
    op.create_table(
        "tv_config",
        sa.Column("resident_id", psql.UUID(as_uuid=False), sa.ForeignKey("care.residents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ambient_rotation", sa.Integer()),
        sa.Column("rail", sa.String(length=50)),
        sa.Column("quiet_hours", sa.String(length=50)),
        sa.Column("default_vibe", sa.String(length=50)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="care",
    )

    # ===========================
    # MUSIC
    # ===========================
    op.create_table(
        "music_devices",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("room", sa.String(length=100)),
        sa.Column("name", sa.String(length=200)),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("capabilities", sa.Text()),
        sa.PrimaryKeyConstraint("provider", "device_id", name="pk_music_devices"),
        schema="music",
    )
    op.create_table(
        "music_tokens",
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("access_token", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token", sa.LargeBinary()),
        sa.Column("scope", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("user_id", "provider", name="pk_music_tokens"),
        schema="music",
    )
    op.create_table(
        "music_preferences",
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("default_provider", sa.String(length=40)),
        sa.Column("quiet_start", sa.Time(), nullable=False, server_default=sa.text("'22:00'::time")),
        sa.Column("quiet_end", sa.Time(), nullable=False, server_default=sa.text("'07:00'::time")),
        sa.Column("quiet_max_volume", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("allow_explicit", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema="music",
    )
    op.create_table(
        "music_sessions",
        sa.Column("session_id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="SET NULL")),
        sa.Column("room", sa.String(length=100)),
        sa.Column("provider", sa.String(length=40)),
        sa.Column("device_id", sa.String(length=128)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        schema="music",
    )
    op.create_table(
        "music_queue",
        sa.Column("session_id", psql.UUID(as_uuid=False), sa.ForeignKey("music.music_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40)),
        sa.Column("entity_type", sa.String(length=40)),
        sa.Column("entity_id", sa.String(length=128)),
        sa.Column("meta", psql.JSONB()),
        sa.PrimaryKeyConstraint("session_id", "position", name="pk_music_queue"),
        schema="music",
    )
    op.create_table(
        "music_feedback",
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("user_id", "track_id", "provider", "ts", name="pk_music_feedback"),
        schema="music",
    )

    # ===========================
    # TOKENS
    # ===========================
    op.create_table(
        "third_party_tokens",
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("access_token", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token", sa.LargeBinary()),
        sa.Column("scope", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("user_id", "provider", name="pk_third_party_tokens"),
        schema="tokens",
    )

    # ===========================
    # AUDIT
    # ===========================
    op.create_table(
        "audit_log",
        sa.Column("id", psql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.users.id", ondelete="SET NULL")),
        sa.Column("session_id", psql.UUID(as_uuid=False), sa.ForeignKey("auth.sessions.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("meta", psql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="audit",
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_log", schema="audit")

    op.drop_table("third_party_tokens", schema="tokens")

    op.drop_table("music_feedback", schema="music")
    op.drop_table("music_queue", schema="music")
    op.drop_table("music_sessions", schema="music")
    op.drop_table("music_preferences", schema="music")
    op.drop_table("music_tokens", schema="music")
    op.drop_table("music_devices", schema="music")

    op.drop_table("tv_config", schema="care")
    op.drop_table("contacts", schema="care")
    op.drop_table("care_sessions", schema="care")
    op.drop_table("alert_events", schema="care")
    op.drop_table("alerts", schema="care")
    op.drop_table("devices", schema="care")
    op.drop_table("caregiver_resident", schema="care")
    op.drop_table("caregivers", schema="care")
    op.drop_table("residents", schema="care")

    op.drop_table("user_stats", schema="users")

    op.drop_table("pat_tokens", schema="auth")
    op.drop_table("auth_identities", schema="auth")
    op.drop_table("sessions", schema="auth")
    op.drop_table("devices", schema="auth")
    op.drop_table("users", schema="auth")

    # Optionally drop schemas (keep extension around)
    for schema in ("audit", "tokens", "music", "care", "users", "auth"):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')

