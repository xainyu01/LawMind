# 第六阶段：高级功能与系统优化

本阶段目标：实现 LLM 意图分类、法条时效性检查、监控接口，优化系统性能，使系统达到生产级水平。

**状态：✅ 已完成**

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────┐
│                  app.py (Streamlit)              │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  聊天界面     │  │  文件上传     │             │
│  │  (已完成)     │  │  (已完成)     │             │
│  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                      │
│  ┌──────▼─────────────────▼───────┐             │
│  │       用户反馈 (已完成)          │             │
│  │       👍 / 👎 → feedback.jsonl  │             │
│  └─────────────────────────────────┘             │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│              Phase 6 新增模块                     │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  app/rag/generator.py                   │    │
│  │  - LLM 意图分类（Prompt 替换关键词）✅   │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  app/rag/vector_store.py                │    │
│  │  - 法条时效性过滤（元数据标注）✅         │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  app/api/routes.py                      │    │
│  │  - Prometheus 监控指标暴露 ✅            │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

## 2. LLM 意图分类

### 2.1 目标

用轻量 LLM Prompt 替换当前关键词方案，提升意图识别准确率。

### 2.2 当前实现

`app/rag/generator.py` 使用关键词匹配：
```python
def classify_intent(query: str) -> str:
    # 关键词匹配：法条查询、案例分析、合同审查、闲聊
```

### 2.3 改进方案

使用 DeepSeek 轻量 Prompt 分类：

```python
INTENT_PROMPT = """请判断用户问题的意图类型，只返回类型名称：
- statute_lookup: 查询具体法条
- case_analysis: 分析案例或判例
- legal_qa: 法律知识问答
- contract_review: 合同审查
- chitchat: 闲聊

用户问题：{query}
意图类型："""
```

### 2.4 优势

- 准确率更高（理解语义而非关键词）
- 支持更复杂的意图表达
- 可扩展新的意图类型

---

## 3. 法条时效性检查

### 3.1 目标

元数据标注法条的颁布/废止日期，检索时自动过滤已废止法条。

### 3.2 数据模型

在文档入库时添加元数据：
```python
metadata = {
    "source": "民法典",
    "effective_date": "2021-01-01",  # 施行日期
    "status": "active",              # active / repealed / amended
    "repealed_date": null,           # 废止日期
    "amended_by": null,              # 修订版本
}
```

### 3.3 实现方案

1. **入库时标注**：`scripts/ingest.py` 解析文档时提取日期信息
2. **检索时过滤**：`app/rag/retriever.py` 查询时添加过滤条件
3. **前端提示**：显示法条时效性状态

### 3.4 过滤逻辑

```python
# 检索时过滤已废止法条
filter_condition = {
    "$or": [
        {"status": "active"},
        {"status": "amended"}
    ]
}
```

---

## 4. 监控接口

### 4.1 目标

暴露 Prometheus 指标，支持 Grafana 可视化监控。

### 4.2 核心指标

| 指标名称 | 类型 | 说明 |
|----------|------|------|
| `rag_requests_total` | Counter | 总请求数 |
| `rag_request_duration_seconds` | Histogram | 请求耗时 |
| `rag_retrieval_duration_seconds` | Histogram | 检索耗时 |
| `rag_llm_duration_seconds` | Histogram | LLM 生成耗时 |
| `rag_cache_hits_total` | Counter | 缓存命中次数 |
| `rag_intent_distribution` | Counter | 意图分布 |

### 4.3 实现方案

使用 `prometheus_client` 库：

```python
from prometheus_client import Counter, Histogram, generate_latest

# 定义指标
REQUEST_COUNT = Counter('rag_requests_total', 'Total requests')
REQUEST_DURATION = Histogram('rag_request_duration_seconds', 'Request duration')

# /metrics 端点
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## 5. 性能优化

### 5.1 检索优化

- **BM25 索引缓存**：已实现（`data/bm25_cache/`）
- **向量检索批量查询**：支持批量 embedding
- **重排序缓存**：对相同 query+context 缓存重排序结果

### 5.2 LLM 优化

- **Prompt 缓存**：相似问题复用 Prompt
- **流式输出**：已实现（`generate_stream`）
- **并发控制**：限制同时请求数

### 5.3 系统优化

- **异步处理**：入库任务异步执行
- **连接池**：复用 HTTP 连接（DeepSeek API）
- **内存管理**：定期清理过期缓存

---

## 6. 验证步骤

### 6.1 LLM 意图分类

```bash
# 测试意图分类准确性
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"民法典第1043条规定了什么"}'
# 期望：intent = statute_lookup
```

### 6.2 法条时效性检查

```bash
# 入库带时效性标注的文档
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py data/docs/

# 检索时应过滤已废止法条
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py "查询内容"
```

### 6.3 监控接口

```bash
# 访问 metrics 端点
curl http://localhost:8000/metrics
# 期望：返回 Prometheus 格式的指标数据
```

---

## 7. 阶段检查清单

- [x] `app/rag/generator.py` LLM 意图分类（替换关键词方案）
- [x] `app/rag/vector_store.py` 法条时效性元数据支持
- [x] `scripts/ingest.py` 入库时标注时效性信息
- [x] `app/rag/retriever.py` 检索时过滤已废止法条
- [x] `app/api/routes.py` Prometheus 监控接口
- [ ] 性能测试与优化
- [x] 文档更新（进度.md、开发指南.md）

---

## 8. 文件清单（Phase 6 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/rag/generator.py` | 修改 | 添加 LLM 意图分类 |
| `app/rag/vector_store.py` | 修改 | 添加时效性过滤支持 |
| `scripts/ingest.py` | 修改 | 入库时标注时效性元数据 |
| `app/api/routes.py` | 修改 | 添加 /metrics 端点 |
| `app/core/config.py` | 修改 | 添加监控配置项 |
| `文档/phase6-高级功能.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 6 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

**下一阶段预告：第七阶段——生产部署（Docker 容器化、Nginx 反向代理、CI/CD 流水线、日志系统）。**
