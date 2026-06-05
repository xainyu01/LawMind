# 第五阶段：前端完善与系统评估

本阶段目标：完善 Streamlit 前端交互（文件上传、用户反馈），搭建 RAGAS 风格评测框架量化系统质量，补齐 Phase 1-4 遗留的工程细节，使系统达到可演示、可评估的完整状态。

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────┐
│                  app.py (Streamlit)              │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │  聊天界面     │  │  文件上传     │             │
│  │  (已有)       │  │  (新增)       │             │
│  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                      │
│  ┌──────▼─────────────────▼───────┐             │
│  │       用户反馈 (新增)            │             │
│  │       👍 / 👎 → feedback.jsonl  │             │
│  └─────────────────────────────────┘             │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│              scripts/eval_ragas.py (新增)         │
│  RAGAS 风格评测：Faithfulness / Relevancy /       │
│  Precision / Recall，DeepSeek 作为评判 LLM       │
└─────────────────────────────────────────────────┘
```

---

## 2. RAGAS 风格评测 `scripts/eval_ragas.py`

### 2.1 背景

原计划使用 `ragas` 库，但 ragas 0.2.x/0.3.x 依赖 `langchain_community.chat_models.vertexai`，而 `langchain-community` 已被 sunset，该模块不存在于当前版本。因此采用自定义实现 RAGAS 风格评测。

### 2.2 评测指标

| 指标 | 说明 | 计算方式 |
|------|------|----------|
| **Faithfulness** | 答案中的声明是否被上下文支持 | LLM 提取声明 → 逐条检查 → 支持比例 |
| **Answer Relevancy** | 答案与问题的相关程度 | LLM 打分 0-10 → 归一化 |
| **Context Precision** | 检索上下文中相关比例 | 文本重叠度判断相关性 |
| **Context Recall** | 标准答案被上下文覆盖比例 | LLM 提取要点 → 逐条检查覆盖 |

### 2.3 评测流程

```
加载评测数据集 (JSON)
  → 对每个 question 执行 RAG 管线（检索 → 重排序 → 生成）
  → 调用 DeepSeek 评判 LLM 计算 4 项指标
  → 汇总平均分 → 保存详细结果
```

### 2.4 评测数据集 `data/eval/legal_eval_dataset.json`

基于已入库的《民法典》节选，覆盖：
- 婚姻家庭（离婚条件、夫妻义务）
- 民事法律行为（有效条件）
- 法条施行时间

共 10 道题目，每题包含 `question`、`ground_truth`、`ground_truth_contexts`。

### 2.5 核心接口

```python
# 评测指标计算
def compute_faithfulness(answer: str, contexts: List[str]) -> float
def compute_answer_relevancy(question: str, answer: str) -> float
def compute_context_precision(retrieved_contexts: List[str], ground_truth_contexts: List[str]) -> float
def compute_context_recall(retrieved_contexts: List[str], ground_truth: str) -> float

# RAG 管线调用
def run_rag_pipeline(question: str) -> Dict  # 返回 {answer, contexts, intent}
```

### 2.6 运行方式

```bash
# 标准运行
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py

# 详细输出（显示每个问题的回答）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py --verbose

# 自定义数据集
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py --dataset data/eval/custom.json
```

### 2.7 输出格式

终端输出汇总指标，详细结果保存到 `data/eval/eval_results.json`：

```json
{
  "summary": {
    "faithfulness": 0.55,
    "answer_relevancy": 0.87,
    "context_precision": 0.90,
    "context_recall": 0.60
  },
  "overall": 0.73,
  "details": [...]
}
```

---

## 3. 文件上传功能 `app.py`

### 3.1 目标

Streamlit 侧边栏添加文件上传组件，用户上传 PDF/Word/TXT 文档后自动解析并入库到 ChromaDB。

### 3.2 设计

```
侧边栏
  └── st.file_uploader("上传法律文档", type=["pdf", "docx", "txt"])
        → 保存到 data/docs/
        → 调用 document_loader 解析
        → 调用 embedding + vector_store 入库
        → 显示成功/失败状态
        → 触发 retriever 重建 BM25 索引
```

### 3.3 复用模块

| 模块 | 接口 | 用途 |
|------|------|------|
| `app/rag/document_loader.py` | `load_and_split(file_path)` | 解析文档并分段 |
| `app/rag/embedding.py` | `BgeEmbedding.encode(texts)` | 向量化 |
| `app/rag/vector_store.py` | `add_documents(ids, docs, metas, embeddings)` | 入库 ChromaDB |

### 3.4 注意事项

- 上传文件保存到 `data/docs/` 后再解析（避免内存文件路径问题）
- 入库完成后需重置 `retriever._loaded = False`，强制下次查询重建 BM25 索引
- 显示入库文档数和分段数给用户

---

## 4. 用户反馈收集 `app.py`

### 4.1 目标

每次 LLM 回答后显示 👍 / 👎 按钮，用户反馈记录到 `data/feedback.jsonl`。

### 4.2 数据格式

```json
{
  "timestamp": "2026-06-05T14:30:00",
  "session_id": "abc123",
  "query": "离婚需要什么条件",
  "answer": "根据《民法典》第1079条...",
  "rating": "positive",
  "intent": "statute_lookup"
}
```

### 4.3 实现方式

```python
# 在每条 assistant 消息下方添加
col1, col2 = st.columns(2)
with col1:
    if st.button("👍", key=f"pos_{msg_idx}"):
        save_feedback(session_id, query, answer, "positive")
with col2:
    if st.button("👎", key=f"neg_{msg_idx}"):
        save_feedback(session_id, query, answer, "negative")
```

### 4.4 反馈文件

- 路径：`data/feedback.jsonl`（JSONL 格式，逐行追加）
- 后续可用于：构建评测数据集、分析系统薄弱环节、Fine-tuning 数据筛选

---

## 5. 验证步骤

### 5.1 RAGAS 评测

```bash
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py
# 期望：输出 4 项指标 + overall 分数
```

### 5.2 文件上传

```bash
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
# 侧边栏上传 PDF → 显示入库成功 → 检索验证
```

### 5.3 用户反馈

```bash
# Streamlit 中提问 → 点击 👍 → 检查 feedback.jsonl
cat data/feedback.jsonl
# 期望：包含刚记录的反馈条目
```

---

## 6. 阶段检查清单

- [x] `scripts/eval_ragas.py` RAGAS 风格评测脚本
- [x] `data/eval/legal_eval_dataset.json` 评测数据集（10 题）
- [x] `data/eval/eval_results.json` 评测结果输出
- [ ] `app.py` 文件上传功能（侧边栏）
- [ ] `app.py` 用户反馈按钮（👍 / 👎）
- [ ] `data/feedback.jsonl` 反馈数据文件
- [ ] 文档更新（进度.md、开发指南.md）

---

## 7. 文件清单（Phase 5 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/eval_ragas.py` | 新建 | RAGAS 风格评测脚本 |
| `data/eval/legal_eval_dataset.json` | 新建 | 法律评测数据集 |
| `data/eval/eval_results.json` | 新建 | 评测结果（自动生成） |
| `app.py` | 修改 | 添加文件上传 + 用户反馈 |
| `data/feedback.jsonl` | 新建 | 反馈数据（自动生成） |
| `文档/phase5-前端与评估.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 5 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

**下一阶段预告：第六阶段——高级功能（LLM 意图分类、法条时效性检查、监控接口、性能优化）。**
