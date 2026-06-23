"""ORM model registry.

importing this package must import every model module so that `Base.metadata` is fully
populated for alembic autogenerate. add new model modules to `__all__` and the imports
below as they are created.
"""

# phase 1+: from app.models.db.user import User, Session  # noqa: F401

__all__: list[str] = []
