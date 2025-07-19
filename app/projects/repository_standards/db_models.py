from datetime import datetime
from typing import List

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON
from app.shared.database import db


class Owner(db.Model):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String)

    relationships: Mapped[List["Relationship"]] = relationship(
        "Relationship", back_populates="owner"
    )
    assets: Mapped[List["Asset"]] = relationship(
        "Asset",
        secondary="relationships",
        back_populates="owners",
        overlaps="relationships",
    )

    def __repr__(self) -> str:
        return f"<Owner id={self.id}, name={self.name}, relationships={self.relationships}>"


class Asset(db.Model):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String)
    type: Mapped[str] = mapped_column(db.String)
    last_updated: Mapped[datetime] = mapped_column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    data: Mapped[dict] = mapped_column(JSON)

    relationships: Mapped[List["Relationship"]] = relationship(
        "Relationship", back_populates="asset"
    )
    owners: Mapped[List["Owner"]] = relationship(
        "Owner",
        secondary="relationships",
        back_populates="assets",
        overlaps="relationships",
    )

    def __repr__(self) -> str:
        return f"<Asset id={self.id}, name={self.name}, owners={[self.owners]}, relationships={self.relationships}>"


class Relationship(db.Model):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    type: Mapped[str] = mapped_column(db.String)
    assets_id: Mapped[int] = mapped_column(db.ForeignKey("assets.id"))
    owners_id: Mapped[int] = mapped_column(db.ForeignKey("owners.id"))

    asset: Mapped["Asset"] = relationship("Asset", back_populates="relationships")
    owner: Mapped["Owner"] = relationship("Owner", back_populates="relationships")

    def __repr__(self) -> str:
        return f"<Relationship id={self.id}, type={self.type}, assets_id={self.assets_id}, owners_id={self.owners_id}>"
