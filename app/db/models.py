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
    __table_args__ = {"schema": "auth"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
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


class AuthDevice(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "auth"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
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
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.devices.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))

    user: Mapped[AuthUser] = relationship(back_populates="sessions")
    device: Mapped[AuthDevice] = relationship(back_populates="sessions")


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_iss", "provider_sub", name="uq_auth_identity_provider_tuple"
        ),
        {"schema": "auth"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_iss: Mapped[str | None] = mapped_column(String(255))
    provider_sub: Mapped[str | None] = mapped_column(String(255))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
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
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
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


# =====================================================================
# USERS schema
# =====================================================================

class UserStats(Base):
    __tablename__ = "user_stats"
    __table_args__ = {"schema": "users"}

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))


# =====================================================================
# CARE schema
# =====================================================================

class Resident(Base):
    __tablename__ = "residents"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
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
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))

    residents: Mapped[list[Resident]] = relationship(
        secondary="care.caregiver_resident", back_populates="caregivers"
    )


class CaregiverResident(Base):
    __tablename__ = "caregiver_resident"
    __table_args__ = (
        PrimaryKeyConstraint("caregiver_id", "resident_id", name="pk_caregiver_resident"),
        {"schema": "care"},
    )

    caregiver_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.caregivers.id", ondelete="CASCADE"), nullable=False
    )
    resident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="CASCADE"), nullable=False
    )
    primary_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))


class CareDevice(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    resident_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="SET NULL")
    )
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    battery_low_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    battery_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    offline_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    offline_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))

    resident: Mapped[Resident | None] = relationship(back_populates="devices")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
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
        UUID(as_uuid=False), ForeignKey("care.alerts.id", ondelete="CASCADE"), nullable=False
    )
    t: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    type: Mapped[str | None] = mapped_column(String(50))
    meta: Mapped[dict | None] = mapped_column(JSONB)

    alert: Mapped[Alert] = relationship(back_populates="events")


class CareSession(Base):
    __tablename__ = "care_sessions"
    __table_args__ = {"schema": "care"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
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
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    resident_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="CASCADE"), nullable=False
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
        UUID(as_uuid=False), ForeignKey("care.residents.id", ondelete="CASCADE"), primary_key=True
    )
    ambient_rotation: Mapped[int | None] = mapped_column(Integer)
    rail: Mapped[str | None] = mapped_column(String(50))
    quiet_hours: Mapped[str | None] = mapped_column(String(50))
    default_vibe: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    resident: Mapped[Resident] = relationship(back_populates="tv_config")


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
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
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
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    default_provider: Mapped[str | None] = mapped_column(String(40))
    quiet_start: Mapped[str] = mapped_column(Time, nullable=False, server_default=sa.text("'22:00'::time"))
    quiet_end: Mapped[str] = mapped_column(Time, nullable=False, server_default=sa.text("'07:00'::time"))
    quiet_max_volume: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("30"))
    allow_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))


class MusicSession(Base):
    __tablename__ = "music_sessions"
    __table_args__ = {"schema": "music"}

    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
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
        UUID(as_uuid=False), ForeignKey("music.music_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict | None] = mapped_column(JSONB)


class MusicFeedback(Base):
    __tablename__ = "music_feedback"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "track_id", "provider", "ts", name="pk_music_feedback"),
        {"schema": "music"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))


# =====================================================================
# TOKENS schema
# =====================================================================

class ThirdPartyToken(Base):
    __tablename__ = "third_party_tokens"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "provider", name="pk_third_party_tokens"),
        {"schema": "tokens"},
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
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
    __table_args__ = {"schema": "audit"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()")
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("auth.sessions.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

