from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False)

class Obligation(Base):
    __tablename__ = "obligations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    regulation_reference: Mapped[str] = mapped_column(String(150), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    entity: Mapped[Entity] = relationship()
