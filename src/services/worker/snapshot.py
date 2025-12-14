"""
快照服务，用于捕获和存储页面快照。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

from src.core.storage import StorageBackend, get_storage
from src.core.logging import get_logger
from src.services.worker.browser import BrowserManager
from src.services.worker.hasher import CleanHasher

logger = get_logger(__name__)


@dataclass
class SnapshotResult:
    """快照操作结果。"""
    url: str
    oss_path: str
    content_hash: str
    clean_hash: str
    timestamp: datetime
    change_detected: bool
    http_status: int
    error_message: Optional[str] = None
    
    # 文件名 (相对于 oss_path)
    dom_file: str = "dom.html"
    source_file: str = "source.html"
    mhtml_file: str = "page.mhtml"
    screenshot_file: str = "screenshot.png"


class SnapshotService:
    """
    快照捕获服务。
    
    捕获内容:
    - dom.html: 用于提取的清洗后 DOM
    - source.html: 原始响应
    - page.mhtml: 完整页面存档 (CDP)
    - screenshot.png: 可视化证据
    """
    
    def __init__(
        self,
        browser: Optional[BrowserManager] = None,
        storage: Optional[StorageBackend] = None,
        hasher: Optional[CleanHasher] = None
    ):
        self.browser = browser or BrowserManager()
        self.storage = storage or get_storage(use_local=True)
        self.hasher = hasher or CleanHasher()
        self._owns_browser = browser is None
    
    async def start(self) -> None:
        """启动服务。"""
        if self._owns_browser:
            await self.browser.start()
    
    async def stop(self) -> None:
        """停止服务。"""
        if self._owns_browser:
            await self.browser.stop()
    
    async def capture(
        self,
        url: str,
        last_clean_hash: Optional[str] = None
    ) -> SnapshotResult:
        """
        捕获 URL 快照。
        
        Args:
            url: 目标 URL
            last_clean_hash: 用于变更检测的上一次 clean hash
            
        Returns:
            SnapshotResult 包含捕获详情
        """
        timestamp = datetime.now()
        page: Optional[Page] = None
        
        try:
            # 步骤 1: 导航到 URL
            page = await self.browser.new_page()
            http_status = await self.browser.navigate(page, url)
            
            # 检查错误状态
            if http_status >= 400:
                return SnapshotResult(
                    url=url,
                    oss_path="",
                    content_hash="",
                    clean_hash="",
                    timestamp=timestamp,
                    change_detected=False,
                    http_status=http_status,
                    error_message=f"HTTP 错误: {http_status}"
                )
            
            # 步骤 2: 获取内容并计算哈希
            source_html = await self.browser.get_dom_html(page)
            content_hash = self.hasher.compute_content_hash(source_html)
            clean_hash = self.hasher.compute_clean_hash(source_html)
            
            # 步骤 3: 检查变更
            change_detected = last_clean_hash is None or clean_hash != last_clean_hash
            
            # 步骤 4: 生成存储路径
            oss_path = self.storage.generate_path(url, timestamp)
            
            if change_detected:
                # 步骤 5: 捕获额外文件
                dom_html = self.hasher.get_cleaned_dom(source_html)
                mhtml = await self.browser.get_mhtml(page)
                screenshot = await self.browser.get_screenshot(page)
                
                # 步骤 6: 保存文件到存储
                await self.storage.save(f"{oss_path}dom.html", dom_html.encode("utf-8"))
                await self.storage.save(f"{oss_path}source.html", source_html.encode("utf-8"))
                await self.storage.save(f"{oss_path}page.mhtml", mhtml)
                await self.storage.save(f"{oss_path}screenshot.png", screenshot)
                
                logger.info(f"快照已捕获: {url} -> {oss_path}")
            else:
                logger.info(f"未检测到变更: {url}")
            
            return SnapshotResult(
                url=url,
                oss_path=oss_path,
                content_hash=content_hash,
                clean_hash=clean_hash,
                timestamp=timestamp,
                change_detected=change_detected,
                http_status=http_status
            )
            
        except Exception as e:
            logger.error(f"快照失败: {url}, error={e}")
            return SnapshotResult(
                url=url,
                oss_path="",
                content_hash="",
                clean_hash="",
                timestamp=timestamp,
                change_detected=False,
                http_status=0,
                error_message=str(e)
            )
        finally:
            if page:
                await page.close()
    
    async def __aenter__(self) -> "SnapshotService":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
