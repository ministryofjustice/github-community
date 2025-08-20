from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import db


class Acronym(db.Model):
    __tablename__ = "acronyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    abbreviation: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "abbreviation", "definition", name="_abbreviation_definition_uc"
        ),
    )
