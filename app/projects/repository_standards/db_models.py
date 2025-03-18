from datetime import datetime
from typing import List

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.projects.repository_standards.models.repository_info import RepositoryInfo
from app.shared.database import db


class Owner(db.Model):
    __tablename__ = "owner"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String)

    relationships: Mapped[List["Relationship"]] = relationship(
        "Relationship", back_populates="owner"
    )
    assets: Mapped[List["Asset"]] = relationship(
        "Asset",
        secondary="relationship",
        back_populates="owners",
        overlaps="relationships",
    )

    def __repr__(self) -> str:
        return f"<Owner id={self.id}, name={self.name}, relationships={self.relationships}>"


class Asset(db.Model):
    __tablename__ = "asset"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String)
    type: Mapped[str] = mapped_column(db.String)
    last_updated: Mapped[datetime] = mapped_column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    data: Mapped[dict] = mapped_column(JSONB)

    relationships: Mapped[List["Relationship"]] = relationship(
        "Relationship", back_populates="asset"
    )
    owners: Mapped[List["Owner"]] = relationship(
        "Owner",
        secondary="relationship",
        back_populates="assets",
        overlaps="relationships",
    )

    def __repr__(self) -> str:
        return f"<Asset id={self.id}, name={self.name}, owners={[self.owners]}, relationships={self.relationships}>"


class Relationship(db.Model):
    __tablename__ = "relationship"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    type: Mapped[str] = mapped_column(db.String)
    asset_id: Mapped[int] = mapped_column(db.ForeignKey("asset.id"))
    owner_id: Mapped[int] = mapped_column(db.ForeignKey("owner.id"))

    asset: Mapped["Asset"] = relationship("Asset", back_populates="relationships")
    owner: Mapped["Owner"] = relationship("Owner", back_populates="relationships")

    def __repr__(self) -> str:
        return f"<Relationship id={self.id}, type={self.type}, asset_id={self.asset_id}, owner_id={self.owner_id}>"
