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
    type_id: Mapped[int] = mapped_column(db.ForeignKey("owner_types.id"))

    relationships: Mapped[List["Relationship"]] = relationship(
        "Relationship", back_populates="owner"
    )
    type: Mapped["OwnerTypes"] = relationship("OwnerTypes")

    def __repr__(self):
        return f"<Owner id={self.id}, name={self.name}>"


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

    def __repr__(self):
        return f"<Asset id={self.id}, name={self.name}>"


class Relationship(db.Model):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    type: Mapped[str] = mapped_column(db.String)
    assets_id: Mapped[int] = mapped_column(db.ForeignKey("assets.id"))
    owners_id: Mapped[int] = mapped_column(db.ForeignKey("owners.id"))

    asset: Mapped["Asset"] = relationship("Asset", back_populates="relationships")
    owner: Mapped["Owner"] = relationship("Owner", back_populates="relationships")

    def __repr__(self):
        return f"<Relationship id={self.id}, type={self.type}, asset={self.assets_id}, owner={self.owners_id}>"


class OwnerTypes(db.Model):
    __tablename__ = "owner_types"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String)

    def __repr__(self):
        return f"<OwnerTypes id={self.id}, name={self.name}>"
