"""
Talemon 存储模块。
提供本地和 OSS 存储后端的抽象。
"""
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.config import get_settings, OSSSettings
from src.core.logging import get_logger

logger = get_logger(__name__)


class StorageBackend(ABC):
    """存储后端抽象基类。"""
    
    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """
        将内容保存到存储。
        
        Args:
            path: 存储内的相对路径
            content: 要保存的二进制内容
            
        Returns:
            已保存文件的完整路径/URL
        """
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """检查给定路径的文件是否存在。"""
        pass
    
    @abstractmethod
    async def read(self, path: str) -> bytes:
        """从存储读取内容。"""
        pass
    
    def generate_path(self, url: str, timestamp: Optional[datetime] = None) -> str:
        """
        根据 URL 和时间戳生成存储路径。
        
        Args:
            url: 页面 URL
            timestamp: 可选时间戳 (默认为当前时间)
            
        Returns:
            类似 "{url_hash}/{timestamp}/" 的路径
        """
        settings = get_settings()
        url_hash = hashlib.sha1(url.encode()).hexdigest()
        
        if timestamp is None:
            timestamp = datetime.now()
        
        ts_str = timestamp.strftime(settings.oss.path.timestamp_format)
        
        return settings.oss.path.template.format(
            url_hash=url_hash,
            timestamp=ts_str
        )


class LocalStorage(StorageBackend):
    """用于开发/测试的本地文件系统存储后端。"""
    
    def __init__(self, base_dir: str = "./data/oss"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"本地存储初始化于: {self.base_dir.absolute()}")
    
    async def save(self, path: str, content: bytes) -> str:
        """将内容保存到本地文件系统。"""
        full_path = self.base_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        full_path.write_bytes(content)
        logger.debug(f"已保存 {len(content)} 字节到 {full_path}")
        
        return str(full_path)
    
    async def exists(self, path: str) -> bool:
        """检查文件是否存在于本地。"""
        return (self.base_dir / path).exists()
    
    async def read(self, path: str) -> bytes:
        """从本地文件系统读取内容。"""
        full_path = self.base_dir / path
        return full_path.read_bytes()


class OSSStorage(StorageBackend):
    """用于生产环境的阿里云 OSS 存储后端。"""
    
    def __init__(self, settings: Optional[OSSSettings] = None):
        if settings is None:
            settings = get_settings().oss
        
        self.settings = settings
        self._bucket = None
        
        # 延迟导入以避免依赖问题
        try:
            import oss2
            self._oss2 = oss2
        except ImportError:
            logger.warning("未安装 oss2，OSSStorage 将无法工作")
            self._oss2 = None
    
    def _get_bucket(self):
        """获取或创建 OSS bucket 实例。"""
        if self._bucket is None and self._oss2:
            auth = self._oss2.Auth(
                self.settings.access_key_id,
                self.settings.access_key_secret
            )
            self._bucket = self._oss2.Bucket(
                auth,
                self.settings.endpoint,
                self.settings.bucket
            )
        return self._bucket
    
    async def save(self, path: str, content: bytes) -> str:
        """将内容保存到 OSS。"""
        bucket = self._get_bucket()
        if bucket is None:
            raise RuntimeError("OSS 未配置")
        
        full_path = f"{self.settings.prefix}/{path}"
        bucket.put_object(full_path, content)
        
        oss_url = f"oss://{self.settings.bucket}/{full_path}"
        logger.debug(f"已保存 {len(content)} 字节到 {oss_url}")
        
        return oss_url
    
    async def exists(self, path: str) -> bool:
        """检查文件是否存在于 OSS。"""
        bucket = self._get_bucket()
        if bucket is None:
            return False
        
        full_path = f"{self.settings.prefix}/{path}"
        return bucket.object_exists(full_path)
    
    async def read(self, path: str) -> bytes:
        """从 OSS 读取内容。"""
        bucket = self._get_bucket()
        if bucket is None:
            raise RuntimeError("OSS 未配置")
        
        full_path = f"{self.settings.prefix}/{path}"
        result = bucket.get_object(full_path)
        return result.read()


def get_storage(use_local: bool = True) -> StorageBackend:
    """
    获取存储后端实例。
    
    Args:
        use_local: 如果为 True，使用本地存储 (用于测试)
                  如果为 False，使用 OSS 存储 (用于生产)
    """
    if use_local:
        return LocalStorage()
    else:
        return OSSStorage()
