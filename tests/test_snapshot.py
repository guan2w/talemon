"""
快照功能测试用例。

本测试:
1. 从数据库 (main.page 表) 读取 URL
2. 捕获快照并保存到 ./data/oss/
3. 验证文件是否正确创建
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import init_settings
from src.core.database import get_session, init_database, close_database
from src.core.storage import LocalStorage
from src.core.logging import setup_logging
from src.models.page import Page, PageStatus
from src.services.worker import BrowserManager, CleanHasher, SnapshotService

# 测试数据目录
DATA_DIR = Path("./data/oss")


@pytest.fixture(scope="session")
def event_loop():
    """为异步测试创建事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup():
    """配置测试环境。"""
    # 初始化设置
    init_settings()
    setup_logging(level="DEBUG")
    
    # 确保数据目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    yield
    
    # 清理
    asyncio.get_event_loop().run_until_complete(close_database())


@pytest.fixture
def storage():
    """获取本地存储实例。"""
    return LocalStorage(str(DATA_DIR))


@pytest.fixture
def hasher():
    """获取哈希器实例。"""
    return CleanHasher()


class TestCleanHasher:
    """Clean Hash 算法测试。"""
    
    def test_content_hash(self, hasher):
        """测试原始内容哈希。"""
        html = "<html><body>Hello World</body></html>"
        hash1 = hasher.compute_content_hash(html)
        hash2 = hasher.compute_content_hash(html)
        
        assert hash1 == hash2
        assert len(hash1) == 40  # SHA1 十六进制长度
    
    def test_clean_hash_removes_scripts(self, hasher):
        """测试 clean hash 是否移除了脚本。"""
        html_with_script = """
        <html>
            <body>
                <script>console.log('noise')</script>
                <p>Content</p>
            </body>
        </html>
        """
        html_without_script = """
        <html>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        hash1 = hasher.compute_clean_hash(html_with_script)
        hash2 = hasher.compute_clean_hash(html_without_script)
        
        # 移除脚本后哈希应相同
        assert hash1 == hash2
    
    def test_clean_hash_different_content(self, hasher):
        """测试不同内容生成不同哈希。"""
        html1 = "<html><body><p>Content A</p></body></html>"
        html2 = "<html><body><p>Content B</p></body></html>"
        
        hash1 = hasher.compute_clean_hash(html1)
        hash2 = hasher.compute_clean_hash(html2)
        
        assert hash1 != hash2
    
    def test_cleaned_dom(self, hasher):
        """测试 DOM 清洗。"""
        html = """
        <html>
            <head><script>bad</script></head>
            <body>
                <style>.hidden{}</style>
                <p>Good content</p>
            </body>
        </html>
        """
        
        cleaned = hasher.get_cleaned_dom(html)
        
        assert "<script>" not in cleaned
        assert "Good content" in cleaned


class TestLocalStorage:
    """本地存储后端测试。"""
    
    @pytest.mark.asyncio
    async def test_save_and_read(self, storage):
        """测试保存和读取文件。"""
        path = "test/file.txt"
        content = b"Hello, World!"
        
        # 保存
        full_path = await storage.save(path, content)
        assert Path(full_path).exists()
        
        # 读取
        read_content = await storage.read(path)
        assert read_content == content
        
        # 检查存在
        exists = await storage.exists(path)
        assert exists is True
    
    def test_generate_path(self, storage):
        """测试路径生成。"""
        from datetime import datetime
        
        url = "https://example.com/page"
        timestamp = datetime(2025, 12, 6, 14, 30, 25)
        
        path = storage.generate_path(url, timestamp)
        
        # 应包含哈希和时间戳
        assert "/" in path
        assert "251206.143025" in path


class TestSnapshotService:
    """快照服务测试。"""
    
    @pytest.mark.asyncio
    async def test_capture_simple_url(self, storage):
        """测试捕获简单 URL。"""
        async with SnapshotService(storage=storage) as service:
            # 捕获测试 URL
            result = await service.capture("https://example.com")
            
            assert result.url == "https://example.com"
            assert result.http_status == 200
            assert result.content_hash
            assert result.clean_hash
            assert result.change_detected is True  # 首次捕获
            
            # 验证文件已创建
            if result.oss_path:
                assert await storage.exists(f"{result.oss_path}dom.html")
                assert await storage.exists(f"{result.oss_path}source.html")
                assert await storage.exists(f"{result.oss_path}page.mhtml")
                assert await storage.exists(f"{result.oss_path}screenshot.png")
    
    @pytest.mark.asyncio
    async def test_capture_no_change(self, storage):
        """测试未变更内容不被重新保存。"""
        async with SnapshotService(storage=storage) as service:
            # 首次捕获
            result1 = await service.capture("https://example.com")
            
            # 第二次捕获，传入相同哈希
            result2 = await service.capture(
                "https://example.com",
                last_clean_hash=result1.clean_hash
            )
            
            assert result2.change_detected is False
    
    @pytest.mark.asyncio
    async def test_capture_error_handling(self, storage):
        """测试无效 URL 的错误处理。"""
        async with SnapshotService(storage=storage) as service:
            result = await service.capture("https://this-domain-does-not-exist-12345.com")
            
            assert result.error_message is not None
            assert result.change_detected is False


class TestDatabaseIntegration:
    """数据库集成测试。"""
    
    @pytest.mark.asyncio
    async def test_read_pages_and_snapshot(self, storage):
        """
        集成测试: 从 main.page 表读取数据并捕获快照。
        
        本测试需要:
        1. PostgreSQL 运行中
        2. 数据库和表已创建
        3. main.page 表中有一些 URL
        """
        try:
            await init_database()
        except Exception as e:
            pytest.skip(f"数据库不可用: {e}")
        
        from sqlalchemy import select, text
        
        async with get_session() as session:
            # 从数据库查询页面
            try:
                result = await session.execute(
                    select(Page).where(Page.status == PageStatus.PENDING).limit(3)
                )
                pages = result.scalars().all()
            except Exception as e:
                pytest.skip(f"无法查询页面: {e}")
            
            if not pages:
                # 尝试插入测试数据
                pytest.skip("数据库中没有发现页面")
            
            # 为每个页面捕获快照
            async with SnapshotService(storage=storage) as service:
                for page in pages:
                    print(f"\n正在捕获: {page.url}")
                    result = await service.capture(
                        page.url,
                        last_clean_hash=page.last_clean_hash
                    )
                    
                    print(f"  状态: {result.http_status}")
                    print(f"  有变更: {result.change_detected}")
                    print(f"  路径: {result.oss_path}")
                    
                    if result.error_message:
                        print(f"  错误: {result.error_message}")
                    
                    if result.change_detected and result.oss_path:
                        # 验证文件
                        assert await storage.exists(f"{result.oss_path}dom.html")
                        print(f"  文件已保存至: {DATA_DIR / result.oss_path}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
