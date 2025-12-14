# Talemon

可溯源网络数据采集平台。

## 环境管理

本项目使用 [uv](https://github.com/astral-sh/uv) 进行依赖管理。

### 前置要求

- Python 3.12+
- 已安装 `uv` (参见 [uv 安装指南](https://github.com/astral-sh/uv?tab=readme-ov-file#installation))

### 设置

1. **安装依赖**:
   ```bash
   uv sync
   ```
   这将创建一个虚拟环境 `.venv` 并安装锁定的依赖项。

2. **激活环境**:
   - Windows: `.venv\Scripts\activate`
   - Unix/MacOS: `source .venv/bin/activate`

3. **添加依赖**:
   ```bash
   uv add <package_name>
   ```

4. **添加开发依赖**:
   ```bash
   uv add --dev <package_name>
   ```

5. **运行测试**:
   ```bash
   uv run pytest
   ```
