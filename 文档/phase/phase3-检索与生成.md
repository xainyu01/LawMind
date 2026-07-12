# 第三阶段：RAG 检索与 LLM 生成

本阶段目标：实现混合检索（BM25 + 向量）、Cross-Encoder 重排序、DeepSeek LLM 调用、`/chat` 问答接口，打通「提问 → 检索 → 重排序 → 生成 → 溯源」全链路。

---

## 1. 扩展配置 `app/core/config.py`

新增 Phase 3 所需配置项：

```python
# Reranker
RERANKER_MODEL_NAME: str = os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-base")
RERANKER_DEVICE: str = "cuda"

# Retriever
BM25_TOP_K: int = 10
VECTOR_TOP_K: int = 10
FINAL_TOP_K: int = 5

# LLM
LLM_TEMPERATURE: float = 0.1
LLM_MAX_TOKENS: int = 2048

# Redis (Phase 4 预留)
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
```

> 可通过 `.env` 覆盖 `RERANKER_MODEL_NAME` 和 `REDIS_URL`，其余使用合理默认值。

---

## 2. 混合检索 `app/rag/retriever.py`

**HybridRetriever** 类——BM25 关键词检索 + 向量语义检索 + RRF 融合排序。

### 设计要点

| 组件 | 说明 |
|------|------|
| BM25 索引 | 首次查询时从 ChromaDB 读取全部文档，用 jieba 分词后构建 bm25s 索引 |
| 增量更新 | 对比 ChromaDB `collection.count()` 与上次构建时的文档数，不一致则重建 |
| 向量检索 | 复用 `vector_store.search()` |
| RRF 融合 | `score(d) = Σ 1/(60 + rank_i(d))`，k=60 |
| 去重 | 同一文档在两个检索结果中均出现时，RRF 分数自然叠加 |

### 核心接口

```python
from app.rag.retriever import get_retriever

retriever = get_retriever()
results = retriever.search("离婚需要什么条件", top_k=5)
# 返回 List[dict]，每个元素包含 id, content, metadata, rrf_score
```

> `jieba` 已通过 `uv add jieba` 安装，用于中文分词后构建 BM25 索引。

---

## 3. 重排序 `app/rag/reranker.py`

**LegalReranker** 类——加载 `BAAI/bge-reranker-base`，通过 `sentence_transformers.CrossEncoder` 对候选文档重新打分。

### 设计要点

| 要点 | 说明 |
|------|------|
| 模型 | `BAAI/bge-reranker-base`（~400MB） |
| 加载方式 | 惰性单例，首次使用时加载 |
| 输入 | `(query, doc_content)` 对列表 |
| 输出 | 按 `rerank_score` 降序排列的结果 |

### 核心接口

```python
from app.rag.reranker import get_reranker

reranker = get_reranker()
reranked = reranker.rerank("离婚条件", candidates)
# 结果排序，每个元素增加 rerank_score 字段
```

> 与嵌入模型同时加载，合计显存占用 < 1.5GB。

---

## 4. LLM 生成 `app/rag/generator.py`

**LegalGenerator** 类——通过 `openai` SDK 调用 DeepSeek API，使用法律专用 Prompt 模板，强制法条溯源。

### 设计要点

| 要点 | 说明 |
|------|------|
| API | DeepSeek（OpenAI 兼容接口） |
| System Prompt | 法律助手角色 + 严格引用规则 + 不得编造法条 |
| 上下文注入 | 将检索结果格式化为 `[参考法条 N] 来源 + 内容` |
| 意图分类 | 基于关键词的轻量分流（法条查询/案例分析/合同审查/知识问答/闲聊） |
| 闲聊兜底 | 对"你好""你是谁"等预设固定回复，不消耗 LLM 调用 |

### Legal System Prompt 核心约束

1. 所有法律引用必须注明完整法律名称和条文编号
2. 只能引用参考法条中提供的内容，无来源不引用
3. 不得编造、推测不存在的法条
4. 先给结论，再引法条作为依据

### 核心接口

```python
from app.rag.generator import get_generator

generator = get_generator()
result = generator.generate("什么是诉讼时效", contexts)
# 返回 {"answer": "...", "sources": [...], "intent": "legal_qa"}
```

---

## 5. `/chat` 接口 `app/api/routes.py`

### 接口定义

**POST `/api/v1/chat`**

请求体：
```json
{
    "query": "民事诉讼时效是多久？",
    "history": [
        {"role": "user", "content": "我之前问过债务纠纷"},
        {"role": "assistant", "content": "根据《民法典》..."}
    ]
}
```

响应体：
```json
{
    "answer": "根据《中华人民共和国民法典》第188条...",
    "sources": [
        {
            "content": "第一百八十八条 向人民法院请求...",
            "source": "民法典节选.txt",
            "score": 0.0156
        }
    ],
    "intent": "legal_qa"
}
```

### 处理流程

```
用户提问 → 意图分类 → 混合检索(召回10条) → 重排序(取Top5) → LLM生成 → 返回答案+来源
```

### 注册路由

在 `main.py` 中：

```python
from app.api.routes import router as chat_router
app.include_router(chat_router, prefix="/api/v1")
```

---

## 6. 意图路由

当前采用基于关键词的轻量级分类，分为 5 类：

| 意图 | 触发词 | 处理策略 |
|------|--------|----------|
| `statute_lookup` | 第、条、法条、条文 | RAG + 法条原文返回 |
| `case_analysis` | 案例、判决、裁定、被告 | RAG + 相似案例检索 |
| `contract_review` | 合同、审查、违约、签订 | 指定模板 + 条款比对 |
| `legal_qa` | 默认 | RAG + 知识库 |
| `chitchat` | 你好、你是谁（短文本） | 固定话术兜底 |

> 后续可用轻量 Prompt 做更精准的 LLM 意图分类，替换当前关键词方案。

---

## 7. 验证步骤

### 7.1 配置检查

```bash
uv run python -c "from app.core.config import settings; print(settings.RERANKER_MODEL_NAME)"
# 期望输出: BAAI/bge-reranker-base
```

### 7.2 混合检索测试

```bash
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py --hybrid "夫妻义务"
# 期望：看到 BM25 + 向量融合后的结果，含 rrf_score
```

### 7.3 /chat 接口测试

启动服务：
```bash
uv run python main.py
```

调用接口：
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"夫妻之间有什么义务"}'
```

### 7.4 期望响应

- `answer` 包含中文法律回答
- `sources` 数组非空，每个元素有 `content`、`source`、`score`
- `answer` 中引用法条时注明出处（如"根据《民法典》第1043条"）
- `intent` 识别正确

### 7.5 GPU 显存确认

```bash
uv run python -c "
from app.rag.embedding import BgeEmbedding
from app.rag.reranker import get_reranker
import torch
print(f'显存占用: {torch.cuda.memory_allocated() / 1024**2:.0f} MB')
"
# 期望：嵌入 + 重排序合计 < 1.5GB
```

---

## 8. 阶段检查清单

- [ ] `app/core/config.py` 新增 Phase 3 配置项正常加载
- [ ] `app/rag/retriever.py` BM25 + 向量混合检索返回融合结果
- [ ] `app/rag/reranker.py` 加载 `bge-reranker-base` 并重新打分排序
- [ ] `app/rag/generator.py` DeepSeek LLM 返回含法条溯源的回答
- [ ] `app/api/routes.py` POST `/api/v1/chat` 返回 `{answer, sources, intent}`
- [ ] `scripts/search_test.py --hybrid` 支持完整检索测试
- [ ] 闲聊意图命中时不调用 LLM，直接返回预设话术
- [ ] GPU 显存占用 < 1.5GB（嵌入 + 重排序）

---

## 文件清单（Phase 3 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/core/config.py` | 修改 | 新增 reranker/retriever/LLM 配置 |
| `app/rag/retriever.py` | 新建 | BM25 + 向量混合检索，RRF 融合 |
| `app/rag/reranker.py` | 新建 | Cross-Encoder 重排序 |
| `app/rag/generator.py` | 新建 | DeepSeek LLM 调用 + 法律 Prompt + 意图分类 |
| `app/rag/vector_store.py` | 修改 | 新增 `get_all_documents()`、`get_collection_count()` |
| `app/api/__init__.py` | 新建 | 空 init |
| `app/api/routes.py` | 新建 | `/chat` 问答接口 |
| `main.py` | 修改 | 注册 `/api/v1` 路由 |
| `scripts/search_test.py` | 修改 | 新增 `--hybrid` 模式 |

---

**下一阶段预告：第四阶段——对话记忆与语义缓存（Redis 会话管理、语义缓存、法条时效性 TTL）。**
