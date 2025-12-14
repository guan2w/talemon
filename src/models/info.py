"""
PageInfo 模型 - 从快照提取的结构化数据。
"""
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Text, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.snapshot import PageSnapshot


class PageInfo(Base):
    """
    PageInfo 实体，代表从快照提取的数据。
    
    由 Extractor 服务创建。
    对应数据库中的 `page_info` 表。
    """
    __tablename__ = "page_info"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "extractor_version", name="uk_info_snapshot_version"),
        Index("idx_info_snapshot", "snapshot_id"),
        {"schema": "main"}
    )
    
    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("main.page_snapshot.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # 提取的数据
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # 关系
    snapshot: Mapped["PageSnapshot"] = relationship("PageSnapshot", back_populates="info")
    
    def __repr__(self) -> str:
        return f"<PageInfo(id={self.id}, snapshot_id={self.snapshot_id}, version='{self.extractor_version}')>"
