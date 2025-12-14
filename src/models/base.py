"""
Talemon 模型的 SQLAlchemy Base 声明。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 SQLAlchemy 模型的基类。"""
    pass
