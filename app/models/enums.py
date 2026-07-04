from __future__ import annotations

import enum


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class TriggerSource(str, enum.Enum):
    """Откуда взято действие — встроенное (из JSON) или добавленное пользователем."""
    BUILTIN = "builtin"
    CUSTOM = "custom"
