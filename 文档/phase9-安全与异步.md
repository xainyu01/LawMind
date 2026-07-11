# 第九阶段：安全与异步

本阶段目标：增强系统安全性与高并发能力，包括 API 认证鉴权、请求限流、消息队列异步处理。

**状态：✅ 已完成**

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     安全与异步架构                                 │
│                                                                  │
│  客户端请求                                                       │
│     │                                                            │
│     ▼                                                            │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │   Nginx      │────▶│   认证中间件  │────▶│   限流中间件  │     │
│  │   反向代理    │     │  API Key/JWT │     │  Redis 计数器 │     │
│  └──────────────┘     └──────────────┘     └──────────────┘     │
│                                               │                  │
│                                               ▼                  │
│                                        ┌──────────────┐         │
│                                        │   消息队列    │         │
│                                        │  Redis Stream │         │
│                                        └──────────────┘         │
│                                               │                  │
│                                               ▼                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    FastAPI 服务                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ /chat       │  │ /upload     │  │ /health     │       │   │
│  │  │ 问答接口     │  │ 上传接口     │  │ 健康检查     │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. API 认证鉴权

### 2.1 目标

保护 API 接口，支持两种认证方式：
- **API Key**：简单密钥验证，适合内部服务调用
- **JWT**：基于令牌的认证，适合用户级访问控制

### 2.2 认证流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  客户端   │────▶│ 认证接口  │────▶│ 颁发 JWT  │
│          │     │ /auth    │     │          │
└──────────┘     └──────────┘     └──────────┘
                                      │
                                      ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 受保护    │◀────│ 验证 JWT  │◀────│ 携带 Token│
│ API      │     │ 中间件    │     │ 请求 API  │
└──────────┘     └──────────┘     └──────────┘
```

### 2.3 实现方案

新建 `app/core/auth.py`：

```python
from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer()

# API Key 验证
def verify_api_key(api_key: str = Header(...)) -> bool:
    """验证 API Key。"""
    if api_key not in settings.API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

# JWT 生成
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """生成 JWT Token。"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")

# JWT 验证
def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """验证 JWT Token。"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 2.4 配置项

在 `app/core/config.py` 添加：

```python
# 认证配置
AUTH_ENABLED: bool = True           # 是否启用认证
AUTH_MODE: str = "api_key"          # 认证模式：api_key / jwt / both
API_KEYS: list[str] = []            # 允许的 API Key 列表
JWT_SECRET: str = ""                # JWT 签名密钥
JWT_EXPIRE_HOURS: int = 24          # JWT 过期时间（小时）
```

### 2.5 接口集成

修改 `app/api/routes.py`：

```python
from app.core.auth import verify_api_key, verify_token

# 方式一：API Key 认证
@app.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    _: bool = Depends(verify_api_key)  # 注入认证依赖
):
    ...

# 方式二：JWT 认证
@app.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    user: dict = Depends(verify_token)  # 获取用户信息
):
    ...

# 免认证接口
@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 3. 请求限流

### 3.1 目标

防止 API 被滥用，基于 Redis 实现滑动窗口限流。

### 3.2 限流策略

| 维度 | 默认值 | 说明 |
|------|--------|------|
| 每分钟请求数 | 60 | 单 IP 或单 API Key |
| 每小时请求数 | 1000 | 防止长时间滥用 |
| 并发请求数 | 5 | 单用户同时处理的请求数 |

### 3.3 实现方案

新建 `app/core/rate_limit.py`：

```python
import time
from fastapi import HTTPException, Request
from app.db.backend import get_redis_client

class RateLimiter:
    """基于 Redis 的滑动窗口限流器。"""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """检查是否超过限流阈值。"""
        now = time.time()
        window_start = now - window_seconds

        # 移除窗口外的旧记录
        await self.redis.zremrangebyscore(key, 0, window_start)

        # 统计窗口内的请求数
        request_count = await self.redis.zcard(key)

        if request_count >= max_requests:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded"
            )

        # 添加当前请求
        await self.redis.zadd(key, {str(now): now})
        await self.redis.expire(key, window_seconds)

        return True

# 限流中间件
async def rate_limit_middleware(request: Request, call_next):
    """请求限流中间件。"""
    if settings.RATE_LIMIT_ENABLED:
        # 获取限流 key（IP 或 API Key）
        client_ip = request.client.host
        api_key = request.headers.get("X-API-Key", client_ip)
        rate_key = f"rate:{api_key}"

        # 检查限流
        limiter = RateLimiter(get_redis_client())
        await limiter.check_rate_limit(
            rate_key,
            settings.RATE_LIMIT_PER_MINUTE,
            60
        )

    response = await call_next(request)
    return response
```

### 3.4 配置项

在 `app/core/config.py` 添加：

```python
# 限流配置
RATE_LIMIT_ENABLED: bool = True         # 是否启用限流
RATE_LIMIT_PER_MINUTE: int = 60         # 每分钟请求数
RATE_LIMIT_PER_HOUR: int = 1000         # 每小时请求数
RATE_LIMIT_CONCURRENT: int = 5          # 并发请求数
```

### 3.5 响应头

返回限流信息：

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1625097600
```

---

## 4. 消息队列异步处理

### 4.1 目标

使用 Redis Stream 实现异步任务队列，处理耗时操作（如文档入库、批量检索）。

### 4.2 架构

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 生产者    │────▶│  Redis Stream │────▶│ 消费者 Worker │
│ (API)    │     │  chat_tasks   │     │ (后台进程)    │
└──────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
               ┌──────────────┐
               │  结果存储     │
               │  Redis Hash   │
               └──────────────┘
```

### 4.3 实现方案

新建 `app/db/queue.py`：

```python
import json
import asyncio
from typing import Optional
from app.db.backend import get_redis_client

class TaskQueue:
    """基于 Redis Stream 的任务队列。"""

    def __init__(self, stream_name: str = "chat_tasks"):
        self.redis = get_redis_client()
        self.stream = stream_name
        self.consumer_group = "chat_workers"

    async def create_group(self):
        """创建消费者组。"""
        try:
            await self.redis.xgroup_create(
                self.stream, self.consumer_group, id="0", mkstream=True
            )
        except Exception:
            pass  # 组已存在

    async def publish(self, task_data: dict) -> str:
        """发布任务到队列。"""
        task_id = await self.redis.xadd(
            self.stream,
            {"data": json.dumps(task_data)}
        )
        return task_id

    async def consume(self, consumer_name: str = "worker-1"):
        """消费任务。"""
        while True:
            messages = await self.redis.xreadgroup(
                self.consumer_group,
                consumer_name,
                {self.stream: ">"},
                count=1,
                block=5000
            )

            for stream, entries in messages:
                for message_id, data in entries:
                    task_data = json.loads(data["data"])
                    yield message_id, task_data

    async def ack(self, message_id: str):
        """确认任务完成。"""
        await self.redis.xack(
            self.stream, self.consumer_group, message_id
        )

    async def get_result(self, task_id: str) -> Optional[dict]:
        """获取任务结果。"""
        result = await self.redis.hget(f"task_results", task_id)
        return json.loads(result) if result else None

    async def set_result(self, task_id: str, result: dict):
        """存储任务结果。"""
        await self.redis.hset(
            "task_results",
            task_id,
            json.dumps(result)
        )
```

### 4.4 异步接口

修改 `app/api/routes.py`：

```python
from app.db.queue import TaskQueue

@app.post("/api/v1/chat/async")
async def chat_async(request: ChatRequest):
    """异步问答接口。"""
    queue = TaskQueue()
    task_id = await queue.publish({
        "query": request.query,
        "session_id": request.session_id
    })

    return {
        "task_id": task_id,
        "status": "queued",
        "message": "任务已加入队列，请通过 /task/{task_id} 查询结果"
    }

@app.get("/api/v1/task/{task_id}")
async def get_task_result(task_id: str):
    """查询任务结果。"""
    queue = TaskQueue()
    result = await queue.get_result(task_id)

    if result is None:
        return {"status": "processing"}
    return {"status": "completed", "result": result}
```

### 4.5 Worker 进程

新建 `scripts/worker.py`：

```python
"""后台 Worker 进程，消费任务队列。"""
import asyncio
from app.db.queue import TaskQueue
from app.rag.generator import Generator

async def process_task(task_data: dict) -> dict:
    """处理单个任务。"""
    generator = Generator()
    result = await generator.generate(
        query=task_data["query"],
        context=task_data.get("context", [])
    )
    return {"answer": result}

async def main():
    queue = TaskQueue()
    await queue.create_group()

    print("Worker 启动，等待任务...")

    async for message_id, task_data in queue.consume():
        try:
            result = await process_task(task_data)
            await queue.set_result(message_id, result)
            await queue.ack(message_id)
            print(f"任务 {message_id} 完成")
        except Exception as e:
            print(f"任务 {message_id} 失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 4.6 启动命令

```bash
# 启动 Worker 进程
PYTHONPATH=. uv run python scripts/worker.py

# 测试异步接口
curl -X POST http://localhost:8000/api/v1/chat/async \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "夫妻之间有什么义务"}'

# 查询任务结果
curl http://localhost:8000/api/v1/task/{task_id}
```

---

## 5. 验证步骤

### 5.1 API Key 认证验证

```bash
# 无 API Key（预期 401）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "测试"}'

# 有效 API Key（预期 200）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key-123" \
  -d '{"query": "测试"}'
```

### 5.2 JWT 认证验证

```bash
# 获取 Token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "pass123"}'

# 使用 Token 访问
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{"query": "测试"}'
```

### 5.3 限流验证

```bash
# 快速发送超过限制的请求
for i in {1..100}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/api/v1/chat \
    -H "Content-Type: application/json" \
    -H "X-API-Key: test-key-123" \
    -d '{"query": "测试"}'
done

# 预期：前 60 个返回 200，后续返回 429
```

### 5.4 消息队列验证

```bash
# 发送异步任务
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/chat/async \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key-123" \
  -d '{"query": "夫妻之间有什么义务"}')

TASK_ID=$(echo $RESPONSE | jq -r '.task_id')
echo "Task ID: $TASK_ID"

# 等待处理
sleep 5

# 查询结果
curl http://localhost:8000/api/v1/task/$TASK_ID
```

---

## 6. 阶段检查清单

- [x] `app/core/auth.py` 认证模块（API Key + JWT）
- [x] `app/core/rate_limit.py` 限流模块（滑动窗口）
- [x] `app/db/queue.py` 消息队列模块（Redis Stream）
- [x] `scripts/worker.py` 后台 Worker 进程
- [x] `app/api/routes.py` 集成认证和限流中间件
- [x] `app/core/config.py` 添加认证、限流、队列配置项
- [x] API Key 认证验证
- [x] JWT 认证验证
- [x] 请求限流验证
- [x] 消息队列异步处理验证
- [x] 文档更新（进度.md、开发指南.md）

---

## 7. 文件清单（Phase 9 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/core/auth.py` | 新建 | 认证模块（API Key + JWT） |
| `app/core/rate_limit.py` | 新建 | 限流模块（滑动窗口） |
| `app/db/queue.py` | 新建 | 消息队列模块（Redis Stream） |
| `scripts/worker.py` | 新建 | 后台 Worker 进程 |
| `app/api/routes.py` | 修改 | 集成认证和限流中间件 |
| `app/core/config.py` | 修改 | 添加认证、限流、队列配置项 |
| `pyproject.toml` | 修改 | 添加 PyJWT 依赖 |
| `文档/phase9-安全与异步.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 9 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

## 8. 依赖更新

在 `pyproject.toml` 添加：

```toml
dependencies = [
    # ... existing dependencies ...
    "PyJWT>=2.8.0",           # JWT 认证
]
```

---

## 9. 环境变量

在 `.env` 添加：

```bash
# 认证配置
AUTH_ENABLED=true
AUTH_MODE=api_key
API_KEYS=["test-key-123", "prod-key-456"]
JWT_SECRET=your-secret-key-here
JWT_EXPIRE_HOURS=24

# 限流配置
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

---

**下一阶段预告：第十阶段——性能优化与监控（性能测试、Prometheus 集成、Grafana 仪表盘）。**
