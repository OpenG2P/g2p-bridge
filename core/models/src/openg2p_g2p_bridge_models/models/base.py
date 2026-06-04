import uuid
from datetime import datetime
from typing import Optional

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class BaseORMModelWithId(BaseORMModel):
    __abstract__ = True

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), default=datetime.now)

    def __init__(self, **kwargs):
        # Populate the primary key eagerly (at construction, not at flush) so that
        # dependent rows built in the same unit-of-work can reference this row's
        # id as a foreign key before the session is flushed. The column-level
        # default above is only applied at flush time, which would leave such FKs
        # NULL when the parent's id is read before commit.
        if kwargs.get("id") is None:
            kwargs["id"] = str(uuid.uuid4())
        super().__init__(**kwargs)
