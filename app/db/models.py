# app/db/models.py
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    Time,
    UniqueConstraint,
    text as sqltext,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------- Base with naming convention ----------
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    __abstract__ = True
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


# =====================================================================
# AUTH schema
# =====================================================================


class AuthUser(Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.Index("idx_auth_users_username", "username"),
        sa.UniqueConstraint("username", name="users_username_key"),
        {"schema": "auth"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    auth_providers: Mapped[str | None] = mapped_column(Text)  # JSON string or CSV

    # relationships
    devices: Mapped[list[AuthDevice]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pat_tokens: Mapped[list[PATToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    device_sessions: Mapped[list[DeviceSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list[Ledger]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthDevice(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "auth"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_name: Mapped[str | None] = mapped_column(String(200))
    ua_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[AuthUser] = relationship(back_populates="devices")
    sessions: Mapped[list[Session]] = relationship(back_populates="device")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "auth"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )

    user: Mapped[AuthUser] = relationship(back_populates="sessions")
    device: Mapped[AuthDevice] = relationship(back_populates="sessions")


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_iss",
            "provider_sub",
            name="uq_auth_identity_provider_tuple",
        ),
        {"schema": "auth"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_iss: Mapped[str | None] = mapped_column(String(255))
    provider_sub: Mapped[str | None] = mapped_column(String(255))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    user: Mapped[AuthUser] = relationship(back_populates="identities")


class PATToken(Base):
    __tablename__ = "pat_tokens"
    __table_args__ = {"schema": "auth"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    exp_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[AuthUser] = relationship(back_populates="pat_tokens")


class DeviceSession(Base):
    __tablename__ = "device_sessions"
    __table_args__ = (
        sa.Index("idx_auth_device_sessions_user_id", "user_id"),
        sa.Index("idx_auth_device_sessions_last_seen", sa.desc("last_seen_at"), postgresql_using="btree"),
        sa.Index("idx_device_sessions_last_seen", "last_seen_at"),
        sa.Index("idx_device_sessions_user_id", "user_id"),
        UniqueConstraint(
            "user_id",
            "ua_hash",
            "ip_hash",
            name="device_sessions_user_id_ua_hash_ip_hash_key",
        ),
        {"schema": "auth"},
    )

    sid: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_name: Mapped[str | None] = mapped_column(String(200))
    ua_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[AuthUser] = relationship(back_populates="device_sessions")


# =====================================================================
# USERS schema
# =====================================================================


class UserStats(Base):
    __tablename__ = "user_stats"
    __table_args__ = (
        sa.Index("idx_users_user_stats_login", "user_id", sa.desc("last_login")),
        {"schema": "users"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


# =====================================================================
# CARE schema
# =====================================================================


class Resident(Base):
    __tablename__ = "residents"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    name: Mapped[str | None] = mapped_column(String(200))

    devices: Mapped[list[CareDevice]] = relationship(back_populates="resident")
    alerts: Mapped[list[Alert]] = relationship(back_populates="resident")
    sessions: Mapped[list[CareSession]] = relationship(back_populates="resident")
    contacts: Mapped[list[Contact]] = relationship(back_populates="resident")
    tv_config: Mapped[TVConfig | None] = relationship(
        back_populates="resident", uselist=False, cascade="all, delete-orphan"
    )
    caregivers: Mapped[list[Caregiver]] = relationship(
        secondary="care.caregiver_resident",
        back_populates="residents",
    )


class Caregiver(Base):
    __tablename__ = "caregivers"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))

    residents: Mapped[list[Resident]] = relationship(
        secondary="care.caregiver_resident", back_populates="caregivers"
    )


class CaregiverResident(Base):
    __tablename__ = "caregiver_resident"
    __table_args__ = (
        PrimaryKeyConstraint(
            "caregiver_id", "resident_id", name="pk_caregiver_resident"
        ),
        {"schema": "care"},
    )

    caregiver_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("care.caregivers.id", ondelete="CASCADE"),
        nullable=False,
    )
    resident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("care.residents.id", ondelete="CASCADE"),
        nullable=False,
    )
    primary_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )


class CareDevice(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    resident_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="SET NULL")
    )
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    battery_low_since: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    battery_notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    offline_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    offline_notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )

    resident: Mapped[Resident | None] = relationship(back_populates="devices")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    resident_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="SET NULL")
    )
    kind: Mapped[str | None] = mapped_column(String(50))
    severity: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(30))
    ack_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    resident: Mapped[Resident | None] = relationship(back_populates="alerts")
    events: Mapped[list[AlertEvent]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = {"schema": "care"}

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("care.alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    t: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    type: Mapped[str | None] = mapped_column(String(50))
    meta: Mapped[dict | None] = mapped_column(JSONB)

    alert: Mapped[Alert] = relationship(back_populates="events")


class CareSession(Base):
    __tablename__ = "care_sessions"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    resident_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(200))
    transcript_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    resident: Mapped[Resident | None] = relationship(back_populates="sessions")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    resident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("care.residents.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int | None] = mapped_column(Integer)
    quiet_hours: Mapped[str | None] = mapped_column(String(50))

    resident: Mapped[Resident] = relationship(back_populates="contacts")


class TVConfig(Base):
    __tablename__ = "tv_config"
    __table_args__ = {"schema": "care"}

    resident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("care.residents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ambient_rotation: Mapped[int | None] = mapped_column(Integer)
    rail: Mapped[str | None] = mapped_column(String(50))
    quiet_hours: Mapped[str | None] = mapped_column(String(50))
    default_vibe: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    resident: Mapped[Resident] = relationship(back_populates="tv_config")


# =====================================================================
# CHAT schema
# =====================================================================


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        sa.Index("ix_chat_chat_messages_rid", "rid"),
        {"schema": "chat"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rid: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # Request ID
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # system|user|assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    # Indexes for efficient queries
    __table_args__ = (
        sa.Index("ix_chat_messages_user_rid", "user_id", "rid"),
        sa.Index("ix_chat_messages_created_at", "created_at"),
        {"schema": "chat"},
    )


# =====================================================================
# MUSIC schema
# =====================================================================


class MusicDevice(Base):
    __tablename__ = "music_devices"
    __table_args__ = (
        PrimaryKeyConstraint("provider", "device_id", name="pk_music_devices"),
        {"schema": "music"},
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    room: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    capabilities: Mapped[str | None] = mapped_column(Text)


class MusicToken(Base):
    __tablename__ = "music_tokens"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "provider", name="pk_music_tokens"),
        {"schema": "music"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    access_token: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    refresh_token: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    scope: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class MusicPreferences(Base):
    __tablename__ = "music_preferences"
    __table_args__ = {"schema": "music"}

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_provider: Mapped[str | None] = mapped_column(String(40))
    quiet_start: Mapped[str] = mapped_column(
        Time, nullable=False, server_default=sa.text("'22:00'::time")
    )
    quiet_end: Mapped[str] = mapped_column(
        Time, nullable=False, server_default=sa.text("'07:00'::time")
    )
    quiet_max_volume: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("30")
    )
    allow_explicit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("true")
    )


class MusicSession(Base):
    __tablename__ = "music_sessions"
    __table_args__ = (
        sa.Index("idx_music_sessions_user_id", "user_id"),
        sa.Index("idx_music_sessions_started_at", "started_at"),
        {"schema": "music"},
    )

    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="SET NULL")
    )
    room: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str | None] = mapped_column(String(40))
    device_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class MusicQueue(Base):
    __tablename__ = "music_queue"
    __table_args__ = (
        PrimaryKeyConstraint("session_id", "position", name="pk_music_queue"),
        {"schema": "music"},
    )

    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("music.music_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict | None] = mapped_column(JSONB)


class MusicFeedback(Base):
    __tablename__ = "music_feedback"
    __table_args__ = (
        PrimaryKeyConstraint(
            "user_id", "track_id", "provider", "ts", name="pk_music_feedback"
        ),
        sa.Index("idx_music_feedback_user_track", "user_id", "track_id", "provider"),
        sa.Index("idx_music_feedback_ts", sa.desc("ts"), postgresql_using="btree"),
        {"schema": "music"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    track_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class MusicState(Base):
    __tablename__ = "music_states"
    __table_args__ = (
        sa.Index("idx_music_states_updated_at", "updated_at", postgresql_using="btree"),
        {"schema": "music"},
    )

    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("music.music_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    # Relationship to session
    session: Mapped[MusicSession] = relationship(back_populates="state")


# Add back-reference to MusicSession
MusicSession.state = relationship("MusicState", back_populates="session", uselist=False)


# =====================================================================
# TOKENS schema
# =====================================================================

# =====================================================================
# USER schema (user-specific data)
# =====================================================================


class UserNote(Base):
    __tablename__ = "notes"
    __table_args__ = (
        sa.Index("idx_user_notes_created_at", "created_at"),
        sa.Index("idx_user_notes_user_id", "user_id"),
        {"schema": "user_data"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


# =====================================================================
# STORAGE schema
# =====================================================================


class Ledger(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key", name="ledger_user_id_idempotency_key_key"),
        sa.Index("idx_ledger_idempotency", "idempotency_key"),
        sa.Index("idx_ledger_user_created", "user_id", "created_at"),
        sa.Index("idx_storage_ledger_user_id", "user_id"),
        sa.Index("idx_storage_ledger_user_idempotency", "user_id", "idempotency_key"),
        {"schema": "storage"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float | None] = mapped_column(sa.Numeric(10, 2))
    meta: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    user: Mapped[AuthUser] = relationship(back_populates="ledger_entries")


# =====================================================================
# TOKENS schema
# =====================================================================


class ThirdPartyToken(Base):
    __tablename__ = "third_party_tokens"
    __table_args__ = (
        PrimaryKeyConstraint(
            "user_id", "provider", "provider_sub", name="pk_third_party_tokens"
        ),
        sa.Index("idx_third_party_tokens_provider_sub", "provider_sub"),
        sa.Index("idx_tokens_third_party_user_provider", "user_id", "provider"),
        sa.Index(
            "idx_tokens_third_party_expires",
            "expires_at",
            postgresql_where=sqltext("expires_at IS NOT NULL"),
        ),
        sa.Index(
            "idx_tokens_third_party_expires_at",
            "expires_at",
            postgresql_where=sqltext("expires_at IS NOT NULL"),
        ),
        {"schema": "tokens"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_sub: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    refresh_token: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    scope: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


# =====================================================================
# AUDIT schema
# =====================================================================


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        sa.Index("idx_audit_log_user_id", "user_id"),
        sa.Index("idx_audit_log_created_at", sa.desc("created_at"), postgresql_using="btree"),
        sa.Index("idx_audit_log_created_at_brin", "created_at", postgresql_using="brin"),
        sa.Index("idx_audit_log_event_type", "event_type", sa.desc("created_at"), postgresql_using="btree"),
        sa.Index("idx_audit_log_meta_gin", "meta", postgresql_using="gin"),
        sa.Index("idx_audit_log_recent", sa.desc("created_at"), postgresql_using="btree"),
        sa.Index("idx_audit_log_session_id", "session_id"),
        sa.Index("idx_audit_log_user_session", "user_id", "session_id", sa.desc("created_at"), postgresql_using="btree"),
        {"schema": "audit"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("auth.device_sessions.sid", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
