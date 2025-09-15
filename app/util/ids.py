import uuid

NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")


def to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception:
        return uuid.uuid5(NAMESPACE, str(value))
