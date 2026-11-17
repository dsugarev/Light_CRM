"""Primary keys are UUIDv7 (architecture 4.1): time-ordered, index friendly."""

import uuid


def new_id() -> uuid.UUID:
    return uuid.uuid7()
