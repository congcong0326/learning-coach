from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Problem(Base):
    __tablename__ = "problem"

    id: Mapped[int] = mapped_column(
        ID_TYPE,
        primary_key=True,
        autoincrement=True,
    )
    frontend_id: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        unique=True,
    )
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    translated_title: Mapped[str] = mapped_column(String(240), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    statement_md: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    leetcode_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_paid_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    category_items: Mapped[list[ProblemCategoryItem]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )


class ProblemCategory(Base):
    __tablename__ = "problem_category"

    id: Mapped[int] = mapped_column(
        ID_TYPE,
        primary_key=True,
        autoincrement=True,
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    problem_items: Mapped[list[ProblemCategoryItem]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class ProblemCategoryItem(Base):
    __tablename__ = "problem_category_item"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "problem_id",
            name="uq_problem_category_item_category_problem",
        ),
    )

    id: Mapped[int] = mapped_column(
        ID_TYPE,
        primary_key=True,
        autoincrement=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("problem_category.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problem.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    category: Mapped[ProblemCategory] = relationship(back_populates="problem_items")
    problem: Mapped[Problem] = relationship(back_populates="category_items")
