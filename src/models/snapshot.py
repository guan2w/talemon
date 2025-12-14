"""
PageSnapshot 模型 - 快照存档 (仅当变更时写入)。
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Text, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.page import Page
    from src.models.info import PageInfo


class PageSnapshot(Base):
    """
    PageSnapshot 实体，代表捕获的页面状态。
    
    仅当检测到内容变更时创建。
    对应数据库中的 `page_snapshot` 表。
    """
    __tablename__ = "page_snapshot"
    __table_args__ = (
        UniqueConstraint("page_id", "clean_hash", name="uk_snapshot_page_hash"),
        UniqueConstraint("page_id", "snapshot_timestamp", name="uk_snapshot_page_time"),
        Index("idx_snapshot_page", "page_id"),
        Index("idx_snapshot_time", "snapshot_timestamp"),
        {"schema": "main"}
    )
    
    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键
    page_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("main.page.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # 快照数据
    snapshot_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    oss_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)  # 原始 DOM 的 SHA1
    clean_hash: Mapped[str] = mapped_column(Text, nullable=False)    # 清洗后内容的 SHA1
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # 关系
    page: Mapped["Page"] = relationship("Page", back_populates="snapshots")
    info: Mapped[Optional["PageInfo"]] = relationship(
        "PageInfo", back_populates="snapshot", uselist=False, cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<PageSnapshot(id={self.id}, page_id={self.page_id}, clean_hash='{self.clean_hash[:8]}...')>"
