"""
Page 模型 - URL 资产与调度状态。
"""
from datetime import datetime, timedelta
from enum import Enum as PyEnum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Text, Enum, BigInteger, DateTime, Interval, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.snapshot import PageSnapshot
    from src.models.monitor import PageMonitor


class PageStatus(PyEnum):
    """页面状态枚举。"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAUSED = "PAUSED"


class Page(Base):
    """
    Page 实体，代表被监测的 URL。
    
    对应数据库中的 `page` 表。
    """
    __tablename__ = "page"
    __table_args__ = (
        Index("idx_page_status_schedule", "status", "next_schedule_at", 
              postgresql_where=("status = 'PENDING'")),
        Index("idx_page_domain", "domain"),
        Index("idx_page_heartbeat", "heartbeat_at",
              postgresql_where=("status = 'PROCESSING'")),
        {"schema": "main"}
    )
    
    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # URL 信息
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # sha1(url)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 状态与调度
    status: Mapped[PageStatus] = mapped_column(
        Enum(PageStatus, name="page_status", schema="main"),
        nullable=False,
        default=PageStatus.PENDING
    )
    last_clean_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_schedule_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_interval: Mapped[timedelta] = mapped_column(
        Interval,
        nullable=False,
        default=timedelta(hours=1)
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # 关系
    snapshots: Mapped[List["PageSnapshot"]] = relationship(
        "PageSnapshot", back_populates="page", cascade="all, delete-orphan"
    )
    monitors: Mapped[List["PageMonitor"]] = relationship(
        "PageMonitor", back_populates="page", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Page(id={self.id}, url='{self.url[:50]}...', status={self.status.value})>"
