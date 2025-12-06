-- ============================================================================
-- Talemon 可溯源网络数据采集平台 - 数据库 Schema
-- 版本: 1.0
-- 日期: 2025-12-06
-- ============================================================================

-- 启用 UUID 扩展 (如需要)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 枚举类型定义
-- ============================================================================

-- 页面状态枚举
CREATE TYPE page_status AS ENUM ('PENDING', 'PROCESSING', 'PAUSED');

-- ============================================================================
-- 表定义
-- ============================================================================

-- ----------------------------------------------------------------------------
-- page 表: URL 列表 (资产与状态表)
-- 职责: 存储待监测的 URL 及其调度状态
-- ----------------------------------------------------------------------------
CREATE TABLE page (
    id                  BIGSERIAL       PRIMARY KEY,
    url                 TEXT            NOT NULL,
    hash                TEXT            NOT NULL,       -- sha1(url)
    domain              TEXT            NOT NULL,       -- 域名，用于频率限制
    status              page_status     NOT NULL DEFAULT 'PENDING',
    last_clean_hash     TEXT,                           -- 最后一次 clean_hash
    last_check_at       TIMESTAMPTZ,                    -- 最后检查时间
    next_schedule_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),  -- 下次调度时间
    heartbeat_at        TIMESTAMPTZ,                    -- 心跳时间，用于僵尸检测
    check_interval      INTERVAL        NOT NULL DEFAULT '1 hour',  -- 检查间隔
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    -- 唯一约束
    CONSTRAINT uk_page_url  UNIQUE (url),
    CONSTRAINT uk_page_hash UNIQUE (hash)
);

-- page 表索引
-- 用于调度器获取待处理任务
CREATE INDEX idx_page_status_schedule ON page(status, next_schedule_at) 
    WHERE status = 'PENDING';
-- 用于域名频率限制查询
CREATE INDEX idx_page_domain ON page(domain);
-- 用于僵尸检测
CREATE INDEX idx_page_heartbeat ON page(heartbeat_at) 
    WHERE status = 'PROCESSING';

-- 触发器: 自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_page_updated_at
    BEFORE UPDATE ON page
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ----------------------------------------------------------------------------
-- page_snapshot 表: 快照存档表
-- 职责: 仅当检测到内容变更时写入，存储快照元数据
-- ----------------------------------------------------------------------------
CREATE TABLE page_snapshot (
    id                  BIGSERIAL       PRIMARY KEY,
    page_id             BIGINT          NOT NULL REFERENCES page(id) ON DELETE CASCADE,
    snapshot_timestamp  TIMESTAMPTZ     NOT NULL,       -- 快照时间 (YYMMDD.hhmmss)
    oss_path            TEXT            NOT NULL,       -- OSS 路径: {hash}/{timestamp}/
    content_hash        TEXT            NOT NULL,       -- 原始 DOM 哈希 SHA1
    clean_hash          TEXT            NOT NULL,       -- 清洗后哈希 SHA1
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    -- 唯一约束
    -- UK1: 同一页面 + 同一 clean_hash 只存一份快照 (逻辑去重)
    CONSTRAINT uk_snapshot_page_hash UNIQUE (page_id, clean_hash),
    -- UK2: 与磁盘文件路径对应，便于 clean_hash 算法升级
    CONSTRAINT uk_snapshot_page_time UNIQUE (page_id, snapshot_timestamp)
);

-- page_snapshot 表索引
CREATE INDEX idx_snapshot_page ON page_snapshot(page_id);
CREATE INDEX idx_snapshot_time ON page_snapshot(snapshot_timestamp DESC);

-- ----------------------------------------------------------------------------
-- page_info 表: 提取结果表
-- 职责: 存储从快照中提取的结构化业务数据
-- ----------------------------------------------------------------------------
CREATE TABLE page_info (
    id                  BIGSERIAL       PRIMARY KEY,
    snapshot_id         BIGINT          NOT NULL REFERENCES page_snapshot(id) ON DELETE CASCADE,
    extractor_version   TEXT            NOT NULL,       -- 提取器版本
    data                JSONB           NOT NULL,       -- 提取后的结构化数据
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    -- 唯一约束: 同一快照 + 同一提取器版本只提取一次
    CONSTRAINT uk_info_snapshot_version UNIQUE (snapshot_id, extractor_version)
);

-- page_info 表索引
CREATE INDEX idx_info_snapshot ON page_info(snapshot_id);
CREATE INDEX idx_info_data ON page_info USING GIN (data);  -- JSONB 索引

-- ----------------------------------------------------------------------------
-- page_monitor 表: 监测审计日志表
-- 职责: 记录每一次 Worker 的运行结果，无论是否有变化
-- ----------------------------------------------------------------------------
CREATE TABLE page_monitor (
    id                  BIGSERIAL       PRIMARY KEY,
    page_id             BIGINT          NOT NULL REFERENCES page(id) ON DELETE CASCADE,
    monitor_timestamp   TIMESTAMPTZ     NOT NULL,       -- 监测时间 (YYMMDD.hhmmss)
    content_hash        TEXT,                           -- 原始 DOM 哈希 (可能为空，如请求失败)
    clean_hash          TEXT,                           -- 清洗后哈希 (可能为空)
    change_detected     BOOLEAN         NOT NULL DEFAULT FALSE,  -- 是否检测到变更
    http_status         INTEGER,                        -- HTTP 状态码
    error_message       TEXT,                           -- 错误信息
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    -- 唯一约束: 同一页面同一时间只有一条记录
    CONSTRAINT uk_monitor_page_time UNIQUE (page_id, monitor_timestamp)
);

-- page_monitor 表索引
-- 用于查询某 URL 的监测历史
CREATE INDEX idx_monitor_page_time ON page_monitor(page_id, monitor_timestamp DESC);
-- 用于 Extractor 查询变更记录
CREATE INDEX idx_monitor_change ON page_monitor(change_detected) 
    WHERE change_detected = true;

-- ============================================================================
-- 常用查询示例 (仅供参考，不执行)
-- ============================================================================

/*
-- 1. 调度器获取待处理任务 (乱序 + 域名频控)
SELECT id, url, hash, domain
FROM page
WHERE status = 'PENDING'
  AND next_schedule_at <= NOW()
ORDER BY random()
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- 2. 僵尸任务回收
UPDATE page
SET status = 'PENDING', heartbeat_at = NULL
WHERE status = 'PROCESSING'
  AND heartbeat_at < NOW() - INTERVAL '5 minutes';

-- 3. Worker 更新心跳
UPDATE page
SET heartbeat_at = NOW()
WHERE id = :page_id AND status = 'PROCESSING';

-- 4. 检查 clean_hash 是否变更
SELECT last_clean_hash
FROM page
WHERE id = :page_id;

-- 5. 插入快照记录 (使用 ON CONFLICT 防止重复)
INSERT INTO page_snapshot (page_id, snapshot_timestamp, oss_path, content_hash, clean_hash)
VALUES (:page_id, :timestamp, :oss_path, :content_hash, :clean_hash)
ON CONFLICT (page_id, clean_hash) DO NOTHING;

-- 6. Extractor 查询待提取的快照
SELECT s.id, s.oss_path, s.clean_hash, p.url
FROM page_snapshot s
JOIN page p ON s.page_id = p.id
LEFT JOIN page_info i ON s.id = i.snapshot_id AND i.extractor_version = :version
WHERE i.id IS NULL
LIMIT 50;
*/

-- ============================================================================
-- 完成提示
-- ============================================================================
-- Schema 创建完成。
-- 请确保已配置正确的数据库连接，并使用 psql 或其他工具执行此脚本。
