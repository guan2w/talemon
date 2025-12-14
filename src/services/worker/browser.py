"""
Playwright 浏览器管理器。
处理持久化上下文和扩展加载。
"""
import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Playwright,
    BrowserContext,
    Page,
)

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """
    管理带有扩展的 Playwright 浏览器上下文。
    
    使用持久化上下文以支持 Chrome 扩展，用于：
    - 广告拦截 (uBlock Origin)
    - Cookie 同意处理 (I don't care about cookies)
    """
    
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._settings = get_settings().worker.browser
    
    async def start(self) -> None:
        """启动浏览器上下文。"""
        if self._context is not None:
            return
        
        self._playwright = await async_playwright().start()
        
        # 准备用户数据目录
        user_data_dir = Path(self._settings.user_data_dir)
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 构建启动参数
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        
        # 如果可用，添加扩展
        extensions_dir = Path(self._settings.extensions_dir)
        if extensions_dir.exists():
            extensions = [str(p) for p in extensions_dir.iterdir() if p.is_dir()]
            if extensions:
                launch_args.append(f"--disable-extensions-except={','.join(extensions)}")
                launch_args.append(f"--load-extension={','.join(extensions)}")
                logger.info(f"正在加载扩展: {extensions}")
        
        # 启动持久化上下文
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self._settings.headless,
            args=launch_args,
            executable_path=self._settings.executable_path or None,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Shanghai",
        )
        
        logger.info(f"浏览器上下文已启动 (headless={self._settings.headless})")
    
    async def stop(self) -> None:
        """停止浏览器上下文。"""
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("浏览器上下文已停止")
    
    async def new_page(self) -> Page:
        """在浏览器上下文中创建一个新页面。"""
        if self._context is None:
            await self.start()
        return await self._context.new_page()
    
    async def navigate(
        self,
        page: Page,
        url: str,
        wait_for_network_idle: bool = True
    ) -> int:
        """
        导航到 URL 并等待加载。
        
        Args:
            page: Playwright 页面实例
            url: 目标 URL
            wait_for_network_idle: 是否等待网络空闲
            
        Returns:
            HTTP 状态码
        """
        settings = get_settings().worker
        
        try:
            response = await page.goto(
                url,
                wait_until="networkidle" if wait_for_network_idle else "load",
                timeout=settings.page_timeout_seconds * 1000
            )
            
            if response:
                logger.debug(f"已导航至 {url}, status={response.status}")
                return response.status
            return 0
            
        except Exception as e:
            logger.error(f"导航失败: {url}, error={e}")
            raise
    
    async def get_dom_html(self, page: Page) -> str:
        """获取完整的 DOM HTML 内容。"""
        return await page.content()
    
    async def get_mhtml(self, page: Page) -> bytes:
        """
        使用 CDP 生成 MHTML 快照。
        MHTML 捕获包括资源在内的完整页面。
        """
        cdp = await page.context.new_cdp_session(page)
        try:
            result = await cdp.send("Page.captureSnapshot", {"format": "mhtml"})
            return result["data"].encode("utf-8")
        finally:
            await cdp.detach()
    
    async def get_screenshot(self, page: Page, full_page: bool = True) -> bytes:
        """截取页面截图。"""
        return await page.screenshot(full_page=full_page, type="png")
    
    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
