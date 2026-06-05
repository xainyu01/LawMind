# 第四阶段：对话记忆与语义缓存

本阶段目标：实现 Redis 会话记忆管理、关键信息提取、语义缓存，让系统具备多轮对话能力和 LLM 调用成本优化。

> **Windows 适配**：Redis 在 Windows 上无官方支持，本阶段采用双后端设计——Redis（生产）+ diskcache（本地文件存储），开发环境无需安装 Redis 即可运行全部功能。

---

## 1. 架构概览

```
┌─────────────────────────────────────────────┐
│                  app/db/                     │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │  backend.py  │  │  存储后端抽象层       │  │
│  │              │  │  RedisBackend         │  │
│  │              │  │  DiskBackend          │  │
│  └──────┬──────┘  └──────────┬───────────┘  │
│         │                    │               │
│  ┌──────▼────────────────────▼──────────┐   │
│  │           memory.py                   │   │
│  │  对话记忆（List）+ 上下文提取（Hash）  │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │           cache.py                    │   │
│  │  语义缓存（相似度 > 0.92 命中）        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 2. 存储后端 `app/db/backend.py`

### 设计思路

Windows 无原生 Redis，需要一个抽象层让系统在「有 Redis」和「无 Redis」两种环境下都能运行。

采用策略模式：定义统一接口 `CacheBackend`，两个实现类可无缝切换。

```
CacheBackend (ABC)
  ├── RedisBackend  → 需要 redis-server 运行（Linux/Mac/生产环境）
  └── DiskBackend   → 基于 diskcache，纯 Python，零依赖服务（Windows 开发）
```

### 后端选择逻辑

```python
# 启动时尝试连接 Redis，失败则降级为 DiskBackend
def get_backend() -> CacheBackend:
    try:
        backend = RedisBackend(settings.REDIS_URL)
        backend.ping()  # 快速探测
        return backend
    except (ConnectionError, TimeoutError):
        logger.warning("Redis 不可用，降级为本地磁盘存储")
        return DiskBackend("./data/cache")
```

### 统一接口

```python
class CacheBackend(ABC):
    # 列表操作（对话记忆）
    def lpush(self, key: str, *values: str) -> int: ...
    def lrange(self, key: str, start: int, end: int) -> List[str]: ...
    def ltrim(self, key: str, start: int, end: int) -> None: ...
    def expire(self, key: str, ttl: int) -> None: ...

    # 哈希操作（上下文提取）
    def hset(self, key: str, mapping: dict) -> int: ...
    def hgetall(self, key: str) -> dict: ...

    # 通用操作
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def ping(self) -> bool: ...
```

> DiskBackend 内部用 `diskcache.Index` 模拟 List/Hash 结构。与 Redis 语义一致，后续迁移零改动。

---

## 3. 对话记忆 `app/db/memory.py`

### 3.1 近期对话（Redis List）

每个 `session_id` 对应一个 List，存储最近 N 轮对话。每轮对话序列化为 JSON：

```json
{"role": "user", "content": "离婚需要什么条件"}
{"role": "assistant", "content": "根据《民法典》第1079条..."}
```

**关键操作：**

| 操作 | Redis | DiskBackend |
|------|-------|-------------|
| 追加消息 | `RPUSH session:xxx:messages` | list append |
| 获取最近 N 条 | `LRANGE session:xxx:messages -N -1` | list slice |
| 裁剪到 N 条 | `LTRIM session:xxx:messages -N -1` | list trim |

**配置：**
```python
MAX_MEMORY_TURNS: int = 10  # 每会话最多保留 10 轮对话
MEMORY_TTL: int = 3600      # 会话过期时间 1 小时
```

### 3.2 上下文提取（Redis Hash）

从对话中提取关键信息，作为长期记忆持久化：

| 字段 | 说明 | 示例 |
|------|------|------|
| `law_domains` | 涉及的法律领域 | "婚姻家庭, 合同法" |
| `cited_statutes` | 已引用的法条 | "民法典1043条, 民法典1079条" |
| `user_facts` | 用户陈述的关键事实 | "结婚3年, 感情破裂" |
| `last_intent` | 最近一次意图 | "case_analysis" |

**提取方式**：轻量规则 + 结果累积。每次 LLM 回答后，从 `sources` 和 `intent` 中提取并更新 Hash。

```python
def update_context(session_id: str, query: str, intent: str, sources: list):
    """从本轮对话中提取关键信息并更新上下文 Hash."""
    h = backend.hgetall(f"session:{session_id}:context")
    # 累加法律领域、更新引用法条、保存用户事实
    ...
```

### 核心接口

```python
from app.db.memory import ConversationMemory

memory = ConversationMemory()

# 获取注入 LLM 的上下文摘要
context_text = memory.get_context_for_prompt(session_id)
# 返回: "对话历史:\nUser: ...\nAssistant: ...\n\n关键信息:\n- 法律领域: 婚姻家庭\n- 已引用法条: 民法典1043条"

# 保存一轮对话
memory.save_turn(session_id, user_msg, assistant_msg, intent, sources)

# 获取最近 N 轮原始消息
history = memory.get_history(session_id, last_n=10)
```

---

## 4. 语义缓存 `app/db/cache.py`

### 4.1 缓存流程

```
用户提问 → 向量化 → 搜索缓存 → 相似度 > 0.92?
    ├── 是 → 返回缓存答案（跳过 LLM）
    └── 否 → 正常 RAG 流程 → 结果存入缓存
```

### 4.2 缓存键设计

以用户问题文本的小写规范化作为键：

```python
cache_key = f"cache:{hashlib.md5(query_normalized.encode()).hexdigest()}"
```

### 4.3 TTL 区分策略

法律场景的特殊性——不同类型内容 TTL 不同：

| 内容类型 | TTL | 原因 |
|----------|-----|------|
| 法条查询 | 7 天 | 现行法条相对稳定 |
| 案例分析 | 30 天 | 案例不随时间变化 |
| 法律知识问答 | 7 天 | 通用知识，更新慢 |
| 合同审查建议 | 1 天 | 合同条款可能有新解释 |
| 闲聊 | 不缓存 | 无缓存价值 |

### 4.4 数据结构

缓存值存储完整回答 + 来源：

```json
{
    "answer": "根据《民法典》第1079条...",
    "sources": [...],
    "intent": "legal_qa",
    "cached_at": "2026-06-04T10:30:00"
}
```

### 核心接口

```python
from app.db.cache import SemanticCache

cache = SemanticCache()

# 查找缓存
hit = cache.lookup(query_embedding)
if hit and hit["similarity"] > 0.92:
    return hit["answer"], hit["sources"]

# 存入缓存
cache.store(query_text, answer_data, intent="legal_qa")
```

### 4.5 嵌入缓存优化

每次缓存查找都需要对 query 做嵌入向量化（而这已经在正常 RAG 流程中做过了），避免重复嵌入：缓存查找复用检索阶段已生成的 query embedding。

```python
# 在 routes.py / app.py 中的集成方式：
query_embedding = embedding_model.encode(query)
cached = cache.lookup_by_embedding(query_embedding)  # 复用已有 embedding
if not cached:
    results = retriever.search(query)
    answer = generator.generate(query, results)
    cache.store(query_embedding, answer, intent)
```

---

## 5. 集成到 `/chat` 接口

### 修改 `app/api/routes.py`

在 chat 处理流程中插入缓存检查 + 记忆注入：

```
用户提问
  → 语义缓存检查（跳过或继续）
  → 检索历史上下文（注入 System Prompt）
  → 混合检索 + 重排序 + LLM 生成
  → 保存本轮对话到记忆
  → 存入语义缓存
  → 返回答案
```

### ChatRequest 扩展

```python
class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"  # 新增：用于区分不同会话
    history: List[Message] = []  # 保留：前端可选传入历史
```

### ChatResponse 扩展

```python
class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceDoc]
    intent: str
    cached: bool = False  # 新增：标记是否命中缓存
```

---

## 6. 扩展配置 `app/core/config.py`

新增 Phase 4 配置项：

```python
# Redis / Cache Backend
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_BACKEND_TYPE: str = os.getenv("CACHE_BACKEND", "auto")  # auto / redis / disk
DISK_CACHE_DIR: str = "./data/cache"

# Conversation Memory
MAX_MEMORY_TURNS: int = 10       # 每会话最多保留轮数
SESSION_TTL: int = 3600          # 会话过期时间（秒）

# Semantic Cache
SEMANTIC_CACHE_THRESHOLD: float = 0.92  # 缓存命中相似度阈值
STATUTE_CACHE_TTL: int = 604800        # 法条缓存 7 天（秒）
CASE_CACHE_TTL: int = 2592000          # 案例缓存 30 天
LEGAL_QA_CACHE_TTL: int = 604800       # 知识问答缓存 7 天
CONTRACT_CACHE_TTL: int = 86400        # 合同审查缓存 1 天
```

---

## 7. 验证步骤

### 7.1 后端连通性

```bash
uv run python -c "
from app.db.backend import get_backend
backend = get_backend()
print(f'后端类型: {type(backend).__name__}')
print(f'连通性: {backend.ping()}')
"
# 期望输出: 后端类型: DiskBackend  连通性: True
```

### 7.2 对话记忆

```bash
uv run python -c "
from app.db.memory import ConversationMemory
m = ConversationMemory()
m.save_turn('test_session', '离婚条件是什么', '根据《民法典》第1079条...', 'statute_lookup', [])
history = m.get_history('test_session')
print(f'对话轮数: {len(history)}')
print(f'上下文: {m.get_context_for_prompt(\"test_session\")}')
"
```

### 7.3 语义缓存

```bash
uv run python -c "
from app.db.cache import SemanticCache
c = SemanticCache()
c.store('离婚条件是什么', {'answer': '测试回答', 'sources': [], 'intent': 'statute_lookup'})
hit = c.lookup('离婚条件是什么')
print(f'缓存命中: {hit is not None}')
print(f'缓存内容: {hit}')
"
```

### 7.4 端到端 /chat

```bash
# 启动服务
uv run python main.py

# 同一会话两次提问（第二次应命中缓存）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"离婚需要什么条件","session_id":"test1"}'

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"离婚需要什么条件","session_id":"test1"}'
# 第二次响应中 cached 应为 true
```

### 7.5 Streamlit 集成验证

启动 Streamlit 后验证：
- 多轮对话记忆正确注入
- 语义缓存命中时响应更快
- 侧边栏显示缓存命中状态
- 会话切换后记忆不混淆

```bash
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
```

---

## 8. 阶段检查清单

- [ ] `app/db/backend.py` DiskBackend 正常工作（Windows 无需 Redis）
- [ ] `app/db/memory.py` 对话历史保存与读取
- [ ] `app/db/memory.py` 上下文提取（法律领域、引用法条）
- [ ] `app/db/cache.py` 语义缓存写入与命中
- [ ] `app/db/cache.py` TTL 依内容类型区分
- [ ] `app/api/routes.py` /chat 集成会话记忆
- [ ] `app/api/routes.py` /chat 集成语义缓存（response 标记 cached）
- [ ] `app.py` Streamlit 集成会话记忆与缓存
- [ ] 多轮对话中记忆正确注入 LLM
- [ ] 无 Redis 环境下 DiskBackend 自动降级

---

## 文件清单（Phase 4 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/core/config.py` | 修改 | 新增 Phase 4 配置项 |
| `app/db/__init__.py` | 新建 | 空 init |
| `app/db/backend.py` | 新建 | 双后端抽象（Redis + Disk） |
| `app/db/memory.py` | 新建 | 对话记忆 + 上下文提取 |
| `app/db/cache.py` | 新建 | 语义缓存 |
| `app/api/routes.py` | 修改 | 集成记忆 + 缓存 |
| `app.py` | 修改 | 集成记忆 + 缓存 + session_id |
| `文档/进度.md` | 修改 | 更新 Phase 4 状态 |

---

**下一阶段预告：第五阶段——RAGAS 评测与用户反馈收集。**
