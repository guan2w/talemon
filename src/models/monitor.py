"""
PageMonitor 模型 - 监测审计日志 (每次检查都写入)。
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Text, BigInteger, DateTime, ForeignKey, Boolean, Integer, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.page import Page


class PageMonitor(Base):
    """
    PageMonitor 实体，代表一次监测事件。
    
    每次检查尝试时创建，无论是否检测到变更。
    对应数据库中的 `page_monitor` 表。
    """
    __tablename__ = "page_monitor"
    __table_args__ = (
        UniqueConstraint("page_id", "monitor_timestamp", name="uk_monitor_page_time"),
        Index("idx_monitor_page_time", "page_id", "monitor_timestamp"),
        Index("idx_monitor_change", "change_detected", 
              postgresql_where=("change_detected = TRUE")),
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
    
    # 监测数据
    monitor_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    content_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clean_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    # 关系
    page: Mapped["Page"] = relationship("Page", back_populates="monitors")
    
    def __repr__(self) -> str:
        status = "CHANGED" if self.change_detected else "NO_CHANGE"
        return f"<PageMonitor(id={self.id}, page_id={self.page_id}, status={status})>"
