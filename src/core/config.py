"""
Talemon 配置模块。
从 config.toml 和环境变量加载设置。
"""
import os
from pathlib import Path
from typing import Optional

import tomli
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_toml_config(config_path: Path) -> dict:
    """从 TOML 文件加载配置。"""
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomli.load(f)
    return {}


class GeneralSettings(BaseSettings):
    """通用应用设置。"""
    app_name: str = "talemon"
    env: str = "development"
    log_level: str = "INFO"


class SchedulerSettings(BaseSettings):
    """调度器设置。"""
    enabled: bool = True
    poll_interval_seconds: int = 10
    zombie_check_interval_seconds: int = 300
    zombie_timeout_seconds: int = 300
    batch_size: int = 100


class BrowserSettings(BaseSettings):
    """Playwright 浏览器设置。"""
    headless: bool = True
    user_data_dir: str = "./data/browser_profile"
    extensions_dir: str = "./config/extensions"
    executable_path: str = ""


class RateLimitSettings(BaseSettings):
    """速率限制设置。"""
    default_delay_seconds: int = 5
    max_concurrent_per_domain: int = 2


class WorkerSettings(BaseSettings):
    """采集器设置。"""
    enabled: bool = True
    concurrency: int = 4
    heartbeat_interval_seconds: int = 30
    page_timeout_seconds: int = 60
    network_idle_timeout_seconds: int = 5
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)


class ExtractorSettings(BaseSettings):
    """解析器设置。"""
    enabled: bool = True
    poll_interval_seconds: int = 5
    batch_size: int = 50


class DatabaseSettings(BaseSettings):
    """数据库设置。"""
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # 允许直接配置完整 URL
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    
    # 也可以通过单独的字段配置
    db_host: Optional[str] = Field(default=None, alias="DB_HOST")
    db_port: Optional[int] = Field(default=None, alias="DB_PORT")
    db_user: Optional[str] = Field(default=None, alias="DB_USER")
    db_password: Optional[str] = Field(default=None, alias="DB_PASSWORD")
    db_name: Optional[str] = Field(default=None, alias="DB_NAME")
    
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout_seconds: int = 30
    echo_sql: bool = False

    @model_validator(mode='after')
    def validate_connection_config(self) -> 'DatabaseSettings':
        """验证并构建连接配置。"""
        if self.database_url:
            return self

        # 如果没有 database_url，则必须有全套单独配置
        missing_fields = []
        if not self.db_host: missing_fields.append("DB_HOST")
        if not self.db_port: missing_fields.append("DB_PORT")
        if not self.db_user: missing_fields.append("DB_USER")
        if not self.db_password: missing_fields.append("DB_PASSWORD")
        if not self.db_name: missing_fields.append("DB_NAME")

        if missing_fields:
            raise ValueError(
                f"Missing database configuration. Must provide either DATABASE_URL or all of: {', '.join(missing_fields)}"
            )

        # 默认为 PostgreSQL + AsyncPG
        self.database_url = (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )
        return self


class OSSPathSettings(BaseSettings):
    """OSS 路径设置。"""
    
    template: str = "{url_hash}/{timestamp}/"
    timestamp_format: str = "%y%m%d.%H%M%S"


class OSSSettings(BaseSettings):
    """OSS 存储设置。"""

    model_config = SettingsConfigDict(env_prefix="OSS_")
    
    bucket: str = "talemon-data"
    endpoint: str = "oss-cn-hangzhou.aliyuncs.com"
    prefix: str = "data"
    upload_timeout_seconds: int = 120
    access_key_id: str = Field(default="", alias="OSS_ACCESS_KEY_ID")
    access_key_secret: str = Field(default="", alias="OSS_ACCESS_KEY_SECRET")
    path: OSSPathSettings = Field(default_factory=OSSPathSettings)


class HasherSettings(BaseSettings):
    """Clean Hash 算法设置。"""
    
    strip_tags: list[str] = Field(
        default=["script", "style", "iframe", "noscript", "meta", "link", "svg"]
    )
    extract_attrs: list[str] = Field(default=["href", "src", "alt", "title"])
    ad_selectors: list[str] = Field(
        default=[".ad", ".ads", ".advertisement", "[id*='ad-']", "[class*='ad-']", ".sponsored", ".promo"]
    )


class Settings(BaseSettings):
    """主设置容器。"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    extractor: ExtractorSettings = Field(default_factory=ExtractorSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    oss: OSSSettings = Field(default_factory=OSSSettings)
    hasher: HasherSettings = Field(default_factory=HasherSettings)
    
    @classmethod
    def from_toml(cls, config_path: Optional[Path] = None) -> "Settings":
        """从 TOML 文件和环境变量加载设置。"""
        if config_path is None:
            # 尝试在常见位置找到 config.toml

            for path in [
                Path("config/config.toml"),
                Path("../config/config.toml"),
                Path(__file__).parent.parent.parent / "config" / "config.toml"
            ]:
                if path.exists():
                    config_path = path
                    break
        
        toml_config = {}
        if config_path and config_path.exists():
            toml_config = load_toml_config(config_path)
        
        # 从 TOML 构建嵌套设置
        settings_dict = {}
        
        if "general" in toml_config:
            settings_dict["general"] = GeneralSettings(**toml_config["general"])
        if "scheduler" in toml_config:
            settings_dict["scheduler"] = SchedulerSettings(**toml_config["scheduler"])
        if "worker" in toml_config:
            worker_config = toml_config["worker"].copy()
            if "browser" in worker_config:
                worker_config["browser"] = BrowserSettings(**worker_config["browser"])
            if "rate_limit" in worker_config:
                worker_config["rate_limit"] = RateLimitSettings(**worker_config["rate_limit"])
            settings_dict["worker"] = WorkerSettings(**worker_config)
        if "extractor" in toml_config:
            settings_dict["extractor"] = ExtractorSettings(**toml_config["extractor"])
        if "database" in toml_config:
            settings_dict["database"] = DatabaseSettings(**toml_config["database"])
        if "oss" in toml_config:
            oss_config = toml_config["oss"].copy()
            if "path" in oss_config:
                oss_config["path"] = OSSPathSettings(**oss_config["path"])
            settings_dict["oss"] = OSSSettings(**oss_config)
        if "hasher" in toml_config:
            settings_dict["hasher"] = HasherSettings(**toml_config["hasher"])
        
        return cls(**settings_dict)


# 全局设置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局设置实例。"""
    global _settings
    if _settings is None:
        _settings = Settings.from_toml()
    return _settings


def init_settings(config_path: Optional[Path] = None) -> Settings:
    """从指定配置文件初始化设置。"""
    global _settings
    _settings = Settings.from_toml(config_path)
    return _settings
