# 第七阶段：生产部署

本阶段目标：实现 Docker 容器化、Nginx 反向代理、CI/CD 流水线、日志系统，使系统达到生产部署标准。

**状态：✅ 已完成**

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      生产环境架构                             │
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │   Nginx      │────▶│   FastAPI    │────▶│   Redis      │ │
│  │  反向代理     │     │   应用服务    │     │   缓存/会话   │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
│         │                    │                    │          │
│         │                    ▼                    │          │
│         │            ┌──────────────┐            │          │
│         │            │   ChromaDB   │            │          │
│         │            │   向量数据库  │            │          │
│         │            └──────────────┘            │          │
│         │                                        │          │
│         ▼                                        ▼          │
│  ┌──────────────┐                      ┌──────────────┐     │
│  │   Grafana    │                      │   日志系统    │     │
│  │   监控面板    │                      │  (Loki/ELK)  │     │
│  └──────────────┘                      └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Docker 容器化

### 2.1 目标

Dockerfile + docker-compose 一键部署，支持开发和生产环境。

### 2.2 Dockerfile

```dockerfile
FROM python:3.14-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.3 docker-compose.yml

```yaml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL}
      - LLM_MODEL=${LLM_MODEL}
      - EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}
      - HF_ENDPOINT=${HF_ENDPOINT}
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./data:/app/data
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - app
    restart: unless-stopped

volumes:
  redis_data:
```

---

## 3. Nginx 反向代理

### 3.1 目标

负载均衡、SSL 终止、静态文件服务、请求限流。

### 3.2 nginx.conf

```nginx
events {
    worker_connections 1024;
}

http {
    upstream app {
        server app:8000;
    }

    # 请求限流
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    server {
        listen 80;
        server_name localhost;

        # 重定向到 HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }

    server {
        listen 443 ssl;
        server_name localhost;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # API 代理
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Metrics 端点（仅内网访问）
        location /metrics {
            allow 10.0.0.0/8;
            allow 172.16.0.0/12;
            allow 192.168.0.0/16;
            deny all;
            proxy_pass http://app;
        }

        # 健康检查
        location /health {
            proxy_pass http://app;
        }
    }
}
```

---

## 4. CI/CD 流水线

### 4.1 目标

GitHub Actions 自动化测试与部署。

### 4.2 .github/workflows/ci.yml

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
        run: uv python install 3.14

      - name: Install dependencies
        run: uv sync

      - name: Run linting
        run: uv run ruff check .

      - name: Run tests
        run: uv run pytest

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t legal-rag:${{ github.sha }} .

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Push to Docker Hub
        run: |
          docker tag legal-rag:${{ github.sha }} ${{ secrets.DOCKER_USERNAME }}/legal-rag:latest
          docker push ${{ secrets.DOCKER_USERNAME }}/legal-rag:latest
```

---

## 5. 日志系统

### 5.1 目标

结构化日志、日志聚合、日志查询。

### 5.2 实现方案

使用 Python `structlog` 库输出 JSON 格式日志，配合 Loki + Grafana 查询。

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()

# 使用示例
logger.info("chat_request", query=query, intent=intent, duration=duration)
```

### 5.3 日志字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | ISO 8601 时间戳 |
| `level` | string | 日志级别（INFO/ERROR） |
| `event` | string | 事件名称 |
| `query` | string | 用户查询 |
| `intent` | string | 意图分类 |
| `duration` | float | 请求耗时（秒） |
| `session_id` | string | 会话 ID |
| `cache_hit` | bool | 是否缓存命中 |

---

## 6. 验证步骤

### 6.1 Docker 构建

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f app

# 停止服务
docker compose down
```

### 6.2 Nginx 验证

```bash
# 测试配置
docker compose exec nginx nginx -t

# 访问 API
curl http://localhost/api/v1/chat -X POST -H "Content-Type: application/json" -d '{"query":"你好"}'

# 访问 metrics（内网）
curl http://localhost/metrics
```

### 6.3 CI/CD 验证

```bash
# 推送到 main 分支触发 CI
git push origin main

# 查看 GitHub Actions 状态
gh run list
```

---

## 7. 阶段检查清单

- [x] `Dockerfile` 编写
- [x] `docker-compose.yml` 编写
- [x] `nginx.conf` 编写
- [x] `.github/workflows/ci.yml` 编写
- [x] `app/core/logging.py` 结构化日志配置
- [x] `app/api/routes.py` 集成结构化日志
- [ ] 性能测试与优化
- [x] 文档更新（进度.md、开发指南.md）

---

## 8. 文件清单（Phase 7 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `Dockerfile` | 新建 | Docker 镜像构建文件 |
| `docker-compose.yml` | 新建 | 多容器编排配置 |
| `nginx.conf` | 新建 | Nginx 反向代理配置 |
| `.github/workflows/ci.yml` | 新建 | CI/CD 流水线配置 |
| `app/core/logging.py` | 新建 | 结构化日志配置 |
| `app/api/routes.py` | 修改 | 集成结构化日志 |
| `文档/phase7-生产部署.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 7 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

**下一阶段预告：第八阶段——高级特性（多模态支持、知识图谱、A/B 测试、用户画像）。**
