"""ORM model registry.

importing this package must import every model module so that `Base.metadata` is fully
populated for alembic autogenerate. add new model modules to `__all__` and the imports
below as they are created.
"""

from app.models.db.user import Session, User  # noqa: F401
from app.models.db.profile import (  # noqa: F401
    AnilistProfile,
    SyncJob,
    TasteProfile,
    UserAnimeList,
)

__all__: list[str] = [
    "User",
    "Session",
    "AnilistProfile",
    "UserAnimeList",
    "TasteProfile",
    "SyncJob",
]
