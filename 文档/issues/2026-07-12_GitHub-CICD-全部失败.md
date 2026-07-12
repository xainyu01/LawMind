# 2026-07-12 GitHub Actions CI/CD 全部失败

> 会话时间：2026-07-12
> 状态：**修复中**（CI #9 已推送，仍失败）

---

## 一、问题总览

| 编号 | 问题 | 严重程度 | 状态 |
|------|------|----------|------|
| P1 | ruff 未安装，CI 第一步失败 | 高 | ✅ 已修复（已加入 dev 依赖） |
| P2 | CUDA 版 PyTorch 在 CI 环境安装失败 | 高 | 待修复 |
| P3 | 代码有 48 个 ruff lint 错误 | 中 | 待修复 |
| P4 | build job 依赖 Docker Hub（用户不需要） | 中 | 待修复 |
| P5 | CI 工作流 Python 版本与配置问题 | 高 | 待修复 |

---

## 二、CI/CD 执行流程说明

GitHub Actions **不是传统编译**（Python 是解释型语言）。每次 push 到 main 分支时，GitHub 会自动运行 `.github/workflows/ci.yml` 中定义的流水线：

```
push 到 main → 自动运行以下步骤：
  ① 安装 Python 3.14               ← 可能失败（预览版本，GitHub 支持不稳定）
  ② uv sync（安装依赖）             ← 可能失败（CUDA torch 下载慢/超时）
  ③ ruff check（代码风格检查）       ← ✅ ruff 已安装，但有 48 个 lint 错误
  ④ pytest（运行测试）              ← 前面失败则跳过
  ⑤ docker build（构建镜像）        ← 需要 Docker Hub secrets（用户未配置）
```

每一步失败都会显示红色标记，后续步骤不会执行（因为 `needs: test` 依赖关系）。

---

## 三、问题详情

### P1：ruff 未安装 — CI 第一步就失败

**现象**：
```
error: Failed to spawn: `ruff`
  Caused by: program not found
```

**原因**：CI 运行 `uv run ruff check .`，但 `pyproject.toml` 的 `[dependency-groups] dev` 中只有 `pytest` 和 `requests`，**没有 ruff**。

**当前 dev 依赖配置**：
```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "requests>=2.34.2",
]
```

**缺失**：`ruff` 包。

---

### P2：CUDA 版 PyTorch 在 CI 环境安装失败

**现象**：`uv sync` 阶段下载超时或失败。

**原因**：`pyproject.toml` 中配置了：
```toml
[tool.uv.sources]
torch = { index = "pytorch-cu128" }
```

这强制从 CUDA 12.8 索引安装 PyTorch（包体积约 2GB）。GitHub Actions 的 `ubuntu-latest` runner 没有 GPU，且下载大文件容易超时。

**CI 环境应该使用 CPU 版本的 PyTorch**（体积小、下载快）。

---

### P3：代码有 48 个 ruff lint 错误

**现象**：即使安装了 ruff，`ruff check .` 也会返回 48 个错误。

**错误分布**：
| 错误类型 | 数量 | 可自动修复 |
|----------|------|-----------|
| F401 未使用的 import | 26 | 是 |
| F541 f-string 无占位符 | 8 | 是 |
| F841 未使用的变量 | 4 | 是 |
| E402 import 未在文件顶部 | 1 | 否 |
| 其他 | 9 | 部分 |

**涉及文件**：
- `app/` 目录：7 个文件
- `scripts/` 目录：5 个文件
- `tests/` 目录：8 个文件
- `文档/archive/law_ai-master/`：1 个文件（归档目录，应排除）

**自动修复**：39 个错误可通过 `ruff check --fix` 自动修复。

---

### P4：build job 依赖 Docker Hub（用户不需要）

**现象**：build job 报错 `Login to Docker Hub failed`。

**原因**：build job 需要 `${{ secrets.DOCKER_USERNAME }}` 和 `${{ secrets.DOCKER_PASSWORD }}`，用户没有配置这些 secrets。

**用户实际情况**：没有 Docker Hub 账号，只在自己的服务器上通过 `docker-compose` 部署，不需要推送到 Docker Hub。

---

## 四、修复计划

### ~~第 1 步：`pyproject.toml` — 添加 ruff 到 dev 依赖~~ ✅ 已完成

已在 `pyproject.toml` 中添加 `"ruff>=0.15.21"`。

### 第 2 步：添加 ruff 配置 — 排除归档目录

在 `pyproject.toml` 中添加：
```toml
[tool.ruff]
exclude = ["文档/archive/*"]
```

### 第 3 步：自动修复 ruff 错误

```bash
uv run ruff check . --fix
```

### 第 4 步：`.github/workflows/ci.yml` — 重写 CI 流水线

```yaml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --no-dev
        env:
          # CI 环境用 CPU 版本的 torch
          UV_INDEX: "https://pypi.org/simple/"

      - name: Install dev dependencies
        run: uv sync --group dev

      - name: Run linting
        run: uv run ruff check .

      - name: Run tests
        run: uv run pytest tests/unit/ -v
```

**关键改动**：
- Python 改为 3.12（稳定版本，GitHub Actions 完全支持）
- 通过 `UV_INDEX` 环境变量覆盖 torch 源为 PyPI（CPU 版本）
- 移除 build job（不需要 Docker Hub 推送）
- 只运行单元测试（功能测试需要 GPU/模型/Redis 等外部依赖）

### 第 5 步：`Dockerfile` — 适配 Python 3.12

```dockerfile
FROM python:3.12-slim
```

### 第 6 步：重新生成锁文件

```bash
uv lock
```

---

## 五、涉及文件清单

| 文件 | 操作 |
|------|------|
| `pyproject.toml` | 添加 ruff 依赖、添加 ruff 配置、降低 Python 版本到 3.12 |
| `.github/workflows/ci.yml` | 重写 CI 流水线 |
| `Dockerfile` | 改用 python:3.12-slim |
| `uv.lock` | 重新生成 |
| 多个源文件 | `ruff --fix` 自动修复 lint 错误 |

---

## 六、验证步骤

1. `uv sync` — 确认依赖安装正常
2. `uv run ruff check .` — 确认 lint 通过（0 errors）
3. `uv run pytest tests/unit/ -v` — 确认单元测试通过
4. 提交推送到 main → 观察 GitHub Actions 是否绿色通过
