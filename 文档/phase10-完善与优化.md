# 第十阶段：完善与优化

本阶段目标：完善系统架构，补充对象存储、关系数据库、可视化监控、实时通信、性能优化等生产级功能。

**状态：✅ 用户认证已完成（MySQL + 双令牌）**

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     完善与优化架构                                 │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │   WebSocket  │     │   HTTP API   │     │  Streamlit   │     │
│  │   实时通信    │     │   RESTful    │     │  Web 界面    │     │
│  └──────────────┘     └──────────────┘     └──────────────┘     │
│         │                     │                     │            │
│         └─────────────────────┼─────────────────────┘            │
│                               ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    FastAPI 服务                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ /chat       │  │ /ws/chat    │  │ /documents  │       │   │
│  │  │ 问答接口     │  │ WebSocket   │  │ 文档管理    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────┼──────────────────────────────┐  │
│  │                            ▼                               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │  │ MinIO    │  │  MySQL   │  │ Grafana  │  │ Redis    │  │  │
│  │  │ 对象存储  │  │ 审计日志  │  │ 可视化    │  │ 缓存/队列│  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 对象存储 (MinIO)

### 2.1 目标

使用 MinIO 存储原始法律文档（PDF/Word/TXT），支持版本管理和预签名 URL 下载。

### 2.2 架构

```
用户上传 → FastAPI → MinIO 存储
                    ↓
              返回 object_key
                    ↓
          入库时从 MinIO 读取 → 解析 → 向量化
```

### 2.3 实现方案

新建 `app/storage/minio_client.py`：

```python
from minio import Minio
from minio.error import S3Error
from app.core.config import settings
import io

class MinIOStorage:
    """MinIO 对象存储客户端。"""

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """确保存储桶存在。"""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """上传文件到 MinIO。"""
        self.client.put_object(
            self.bucket,
            object_name,
            io.BytesIO(file_data),
            len(file_data),
            content_type=content_type
        )
        return f"{self.bucket}/{object_name}"

    def download_file(self, object_name: str) -> bytes:
        """从 MinIO 下载文件。"""
        response = self.client.get_object(self.bucket, object_name)
        return response.read()

    def get_presigned_url(
        self,
        object_name: str,
        expires: int = 3600
    ) -> str:
        """生成预签名下载 URL。"""
        return self.client.presigned_get_object(
            self.bucket, object_name, expires=expires
        )

    def delete_file(self, object_name: str):
        """删除文件。"""
        self.client.remove_object(self.bucket, object_name)

    def list_files(self, prefix: str = "") -> list[str]:
        """列出文件。"""
        objects = self.client.list_objects(self.bucket, prefix=prefix)
        return [obj.object_name for obj in objects]
```

### 2.4 API 接口

修改 `app/api/routes.py`：

```python
from app.storage.minio_client import MinIOStorage

@app.post("/api/v1/documents/upload")
async def upload_document(file: UploadFile):
    """上传文档到 MinIO 并触发入库。"""
    storage = MinIOStorage()
    file_data = await file.read()

    # 生成唯一文件名
    object_name = f"{datetime.now().strftime('%Y%m%d')}/{file.filename}"

    # 上传到 MinIO
    storage.upload_file(file_data, object_name, file.content_type)

    # 异步触发入库任务
    queue = TaskQueue()
    await queue.publish({
        "type": "ingest",
        "object_name": object_name,
        "filename": file.filename
    })

    return {
        "status": "uploaded",
        "object_name": object_name,
        "message": "文档已上传，正在处理..."
    }

@app.get("/api/v1/documents/{object_name}/download")
async def download_document(object_name: str):
    """下载文档（预签名 URL）。"""
    storage = MinIOStorage()
    url = storage.get_presigned_url(object_name)
    return {"download_url": url}
```

### 2.5 配置项

在 `app/core/config.py` 添加：

```python
# MinIO 配置
MINIO_ENDPOINT: str = "localhost:9000"
MINIO_ACCESS_KEY: str = "minioadmin"
MINIO_SECRET_KEY: str = "minioadmin"
MINIO_SECURE: bool = False
MINIO_BUCKET: str = "legal-documents"
```

### 2.6 Docker 集成

修改 `docker-compose.yml`：

```yaml
services:
  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio-data:/data
    command: server /data --console-address ":9001"
```

---

## 3. 关系数据库 (MySQL)

### 3.1 目标

使用 MySQL 存储审计日志、用户信息、文档元数据等结构化数据。

### 3.2 数据库设计

```sql
-- 用户表
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    api_key VARCHAR(64) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 对话记录表
CREATE TABLE conversations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(64) NOT NULL,
    user_id BIGINT,
    query TEXT NOT NULL,
    answer TEXT,
    intent VARCHAR(50),
    cached BOOLEAN DEFAULT FALSE,
    latency_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_user (user_id),
    INDEX idx_created (created_at)
);

-- 文档元数据表
CREATE TABLE documents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    object_key VARCHAR(500),
    file_size BIGINT,
    chunk_count INT,
    status ENUM('uploading', 'processing', 'completed', 'failed'),
    uploaded_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

-- 用户反馈表
CREATE TABLE feedback (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT,
    rating ENUM('positive', 'negative'),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- 审计日志表
CREATE TABLE audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT,
    action VARCHAR(50) NOT NULL,
    resource VARCHAR(100),
    details JSON,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_action (action)
);
```

### 3.3 实现方案

新建 `app/db/mysql_client.py`：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

engine = create_engine(settings.MYSQL_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    """获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Models
from sqlalchemy import Column, BigInteger, String, Text, Boolean, Integer, Enum, ForeignKey, TIMESTAMP
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100))
    api_key = Column(String(64), unique=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    query = Column(Text, nullable=False)
    answer = Column(Text)
    intent = Column(String(50))
    cached = Column(Boolean, default=False)
    latency_ms = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())
```

### 3.4 集成到路由

```python
from app.db.mysql_client import get_db, Conversation, AuditLog
from sqlalchemy.orm import Session

@app.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    # ... 处理逻辑 ...

    # 保存对话记录
    conversation = Conversation(
        session_id=request.session_id,
        query=request.query,
        answer=result["answer"],
        intent=result["intent"],
        cached=result.get("cached", False),
        latency_ms=int(latency * 1000)
    )
    db.add(conversation)
    db.commit()

    return result
```

### 3.5 配置项

在 `app/core/config.py` 添加：

```python
# MySQL 配置
MYSQL_URL: str = "mysql+pymysql://root:password@localhost:3306/legal_rag"
```

### 3.6 Docker 集成

修改 `docker-compose.yml`：

```yaml
services:
  mysql:
    image: mysql:8.0
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: legal_rag
    volumes:
      - mysql-data:/var/lib/mysql
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
```

---

## 4. Grafana 可视化监控

### 4.1 目标

使用 Grafana 创建可视化仪表盘，监控系统性能和业务指标。

### 4.2 监控指标

| 仪表盘 | 指标 | 说明 |
|--------|------|------|
| **请求概览** | QPS、响应时间、错误率 | 系统健康度 |
| **检索性能** | BM25/向量检索耗时、RRF 融合耗时 | 检索链路 |
| **LLM 性能** | 生成耗时、Token 使用量 | LLM 调用 |
| **缓存效率** | 命中率、缓存大小 | 语义缓存 |
| **意图分布** | 各意图查询占比 | 业务分析 |

### 4.3 Grafana 配置

新建 `grafana/provisioning/datasources/prometheus.yml`：

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

新建 `grafana/provisioning/dashboards/dashboard.yml`：

```yaml
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /var/lib/grafana/dashboards
```

新建 `grafana/dashboards/rag-overview.json`：

```json
{
  "dashboard": {
    "title": "RAG 系统概览",
    "panels": [
      {
        "title": "请求 QPS",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(rag_requests_total[5m])",
            "legendFormat": "{{intent}}"
          }
        ]
      },
      {
        "title": "响应时间 P95",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(rag_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P95"
          }
        ]
      },
      {
        "title": "缓存命中率",
        "type": "gauge",
        "targets": [
          {
            "expr": "rate(rag_cache_hits_total[5m]) / rate(rag_requests_total[5m])",
            "legendFormat": "命中率"
          }
        ]
      },
      {
        "title": "意图分布",
        "type": "piechart",
        "targets": [
          {
            "expr": "sum by (intent) (rag_requests_total)",
            "legendFormat": "{{intent}}"
          }
        ]
      }
    ]
  }
}
```

### 4.4 Docker 集成

修改 `docker-compose.yml`：

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
```

### 4.5 Prometheus 配置

新建 `prometheus.yml`：

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'rag-api'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'
```

---

## 5. WebSocket 实时通信

### 5.1 目标

支持 WebSocket 连接，实现实时流式问答和进度推送。

### 5.2 实现方案

修改 `app/api/routes.py`：

```python
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

class ConnectionManager:
    """WebSocket 连接管理器。"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)

    async def send_message(self, session_id: str, message: dict):
        ws = self.active_connections.get(session_id)
        if ws:
            await ws.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket 问答接口。"""
    await manager.connect(websocket, session_id)

    try:
        while True:
            # 接收用户消息
            data = await websocket.receive_json()
            query = data.get("query", "")

            # 发送"正在处理"状态
            await manager.send_message(session_id, {
                "type": "status",
                "message": "正在检索..."
            })

            # 检索阶段
            results = await retriever.hybrid_search(query)
            await manager.send_message(session_id, {
                "type": "sources",
                "data": results
            })

            # 流式生成
            await manager.send_message(session_id, {
                "type": "status",
                "message": "正在生成回答..."
            })

            full_answer = ""
            async for chunk in generator.stream_generate(query, results):
                full_answer += chunk
                await manager.send_message(session_id, {
                    "type": "chunk",
                    "data": chunk
                })

            # 完成
            await manager.send_message(session_id, {
                "type": "done",
                "answer": full_answer
            })

    except WebSocketDisconnect:
        manager.disconnect(session_id)
```

### 5.3 客户端使用

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat/user_123');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'status':
            showStatus(data.message);
            break;
        case 'sources':
            showSources(data.data);
            break;
        case 'chunk':
            appendAnswer(data.data);
            break;
        case 'done':
            hideLoading();
            break;
    }
};

ws.send(JSON.stringify({ query: '夫妻之间有什么义务？' }));
```

---

## 6. 法条溯源链接跳转

### 6.1 目标

在回答中标注的法条支持点击跳转到原文位置。

### 6.2 实现方案

修改 `app/rag/generator.py`，在回答中添加锚点链接：

```python
def format_answer_with_links(
    answer: str,
    sources: list[dict]
) -> str:
    """为回答中的法条引用添加链接。"""
    import re

    # 匹配法条引用模式，如"《民法典》第1043条"
    pattern = r'《([^》]+)》第(\d+)条'

    def replace_with_link(match):
        law_name = match.group(1)
        article_num = match.group(2)
        # 查找对应的源文档
        for source in sources:
            if law_name in source.get("source", ""):
                doc_id = source.get("id", "")
                return f'[{match.group(0)}](/documents/{doc_id}#article-{article_num})'
        return match.group(0)

    return re.sub(pattern, replace_with_link, answer)
```

### 6.3 前端支持

在 Streamlit 或 Web 前端中渲染 Markdown 链接：

```python
import streamlit as st

def render_answer(answer: str, sources: list[dict]):
    """渲染带链接的回答。"""
    # 使用 Streamlit 的 Markdown 渲染
    st.markdown(answer, unsafe_allow_html=False)

    # 显示参考法条（可点击）
    with st.expander("参考法条"):
        for source in sources:
            st.markdown(
                f"[{source['source']}](/api/v1/documents/{source['id']}) "
                f"(相关性: {source['score']:.2f})"
            )
```

---

## 7. 性能测试与优化

### 7.1 目标

进行系统性能测试，识别瓶颈并优化。

### 7.2 测试工具

使用 `locust` 进行负载测试：

新建 `tests/locustfile.py`：

```python
from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def chat(self):
        self.client.post("/api/v1/chat", json={
            "query": "夫妻之间有什么义务？",
            "session_id": "test_session"
        })

    @task(1)
    def health(self):
        self.client.get("/health")

    @task(1)
    def metrics(self):
        self.client.get("/metrics")
```

### 7.3 测试命令

```bash
# 安装 locust
uv add locust

# 运行负载测试
uv run locust -f tests/locustfile.py --host http://localhost:8000

# 访问 http://localhost:8089 查看测试界面
```

### 7.4 优化方向

| 瓶颈 | 优化方案 |
|------|----------|
| 向量检索慢 | 增加 HNSW 索引参数调优 |
| LLM 生成慢 | 启用流式输出、减少 max_tokens |
| Redis 延迟 | 使用连接池、批量操作 |
| 内存占用高 | 限制并发数、优化模型加载 |

### 7.5 配置项

在 `app/core/config.py` 添加：

```python
# 性能配置
MAX_CONCURRENT_REQUESTS: int = 10      # 最大并发请求数
REQUEST_TIMEOUT: int = 120             # 请求超时（秒）
BM25_CACHE_SIZE: int = 10000           # BM25 缓存大小
```

---

## 8. 验证步骤

### 8.1 MinIO 存储验证

```bash
# 启动 MinIO
docker-compose up -d minio

# 访问 MinIO 控制台
open http://localhost:9001

# 上传测试文档
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@data/docs/test.txt"

# 下载文档
curl http://localhost:8000/api/v1/documents/test.txt/download
```

### 8.2 MySQL 存储验证

```bash
# 启动 MySQL
docker-compose up -d mysql

# 检查表结构
docker exec -it legal-rag-mysql mysql -u root -p -e "USE legal_rag; SHOW TABLES;"

# 发送请求后检查对话记录
docker exec -it legal-rag-mysql mysql -u root -p -e \
  "USE legal_rag; SELECT * FROM conversations ORDER BY id DESC LIMIT 5;"
```

### 8.3 Grafana 监控验证

```bash
# 启动 Prometheus + Grafana
docker-compose up -d prometheus grafana

# 访问 Grafana
open http://localhost:3000

# 默认账号：admin / admin
# 添加 Prometheus 数据源：http://prometheus:9090
# 导入 RAG 仪表盘
```

### 8.4 WebSocket 验证

```bash
# 使用 wscat 测试
npm install -g wscat
wscat -c ws://localhost:8000/ws/chat/test_session

# 发送消息
> {"query": "夫妻之间有什么义务？"}

# 预期收到流式响应
< {"type": "status", "message": "正在检索..."}
< {"type": "sources", "data": [...]}
< {"type": "chunk", "data": "根据"}
< {"type": "chunk", "data": "《民法典》"}
< {"type": "done", "answer": "根据《民法典》第1043条..."}
```

### 8.5 性能测试验证

```bash
# 启动服务
docker-compose up -d

# 运行负载测试
uv run locust -f tests/locustfile.py --host http://localhost:8000

# 访问 http://localhost:8089 设置并发数和目标
```

---

## 9. 阶段检查清单

### 用户认证系统 ✅

- [x] `app/db/mysql_client.py` MySQL 客户端（SQLAlchemy 引擎、会话、建表）
- [x] `app/db/models.py` ORM 模型（User、RefreshToken）
- [x] `scripts/init_db.py` 数据库初始化脚本（建库建表、创建管理员）
- [x] `app/core/auth.py` 双令牌认证（Access + Refresh、bcrypt 密码哈希）
- [x] `app/api/auth_routes.py` 认证路由（注册/登录/刷新/登出/用户管理）
- [x] `app.py` Streamlit 登录界面（登录/注册/自动刷新/管理员面板）
- [x] `app/core/config.py` MySQL + JWT 双密钥配置
- [x] `main.py` 启动时自动建表、创建管理员
- [x] MySQL 建表验证（users + refresh_tokens）
- [x] 注册/登录/刷新流程验证

### 待实施（可选）

- [ ] `app/storage/minio_client.py` MinIO 客户端
- [ ] `app/api/routes.py` 文档上传/下载接口
- [ ] `grafana/` Grafana 配置与仪表盘
- [ ] `prometheus.yml` Prometheus 配置
- [ ] `app/api/routes.py` WebSocket 接口
- [ ] `tests/locustfile.py` 性能测试脚本
- [ ] 性能测试与优化

---

## 10. 文件清单（Phase 10 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/storage/minio_client.py` | 新建 | MinIO 客户端 |
| `app/db/mysql_client.py` | 新建 | MySQL 客户端与 ORM 模型 |
| `scripts/init.sql` | 新建 | 数据库初始化脚本 |
| `grafana/provisioning/datasources/prometheus.yml` | 新建 | Grafana 数据源配置 |
| `grafana/provisioning/dashboards/dashboard.yml` | 新建 | Grafana 仪表盘配置 |
| `grafana/dashboards/rag-overview.json` | 新建 | RAG 概览仪表盘 |
| `prometheus.yml` | 新建 | Prometheus 配置 |
| `tests/locustfile.py` | 新建 | 性能测试脚本 |
| `app/api/routes.py` | 修改 | 添加文档管理、WebSocket 接口 |
| `app/rag/generator.py` | 修改 | 法条链接生成 |
| `app/core/config.py` | 修改 | 添加 MinIO、MySQL、性能配置 |
| `docker-compose.yml` | 修改 | 添加 MinIO、MySQL、Prometheus、Grafana 服务 |
| `pyproject.toml` | 修改 | 添加 minio、sqlalchemy、pymysql、locust 依赖 |
| `文档/phase10-完善与优化.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 10 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

## 11. 依赖更新

在 `pyproject.toml` 添加：

```toml
dependencies = [
    # ... existing dependencies ...
    "minio>=7.2.0",               # MinIO 对象存储
    "sqlalchemy>=2.0",            # ORM
    "pymysql>=1.1.0",             # MySQL 驱动
    "locust>=2.20.0",             # 性能测试
]
```

---

## 12. 环境变量

在 `.env` 添加：

```bash
# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=legal-documents

# MySQL 配置
MYSQL_URL=mysql+pymysql://root:password@localhost:3306/legal_rag

# Grafana 配置
GF_SECURITY_ADMIN_PASSWORD=admin
```

---

**项目完成：Phase 10 完成后，法律 RAG 系统架构全部实现。**
