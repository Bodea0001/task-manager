from uuid import UUID
from typing import Annotated
from datetime import datetime

from sqlalchemy import func, Identity
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql.sqltypes import BIGINT, Uuid, TIMESTAMP


intpk = Annotated[
    int,
    mapped_column(
        BIGINT, Identity(always=True), primary_key=True, comment="Уникальный идентификатор"
    ),
]

uuidpk = Annotated[
    UUID,
    mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7(), comment="Уникальный идентификатор"
    ),
]

created_at = Annotated[
    datetime,
    mapped_column(
        TIMESTAMP(timezone=True), server_default=func.NOW(), comment="Дата и время создания"
    ),
]
