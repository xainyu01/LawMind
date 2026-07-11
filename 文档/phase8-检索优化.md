# 第八阶段：检索优化

本阶段目标：提升检索质量，包括 MMR 去重、法条结构化分段、法律数据集入库。

**状态：✅ 全部完成**

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        检索优化架构                               │
│                                                                  │
│  用户查询                                                         │
│     │                                                            │
│     ▼                                                            │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │   BM25       │────▶│   RRF 融合   │────▶│   MMR 去重   │     │
│  │   关键词检索  │     │              │     │   提升多样性  │     │
│  └──────────────┘     └──────────────┘     └──────────────┘     │
│         │                                       │                │
│         │                                       ▼                │
│  ┌──────────────┐                        ┌──────────────┐       │
│  │   向量检索    │───────────────────────▶│   重排序      │       │
│  │   语义相似    │                        │ Cross-Encoder │       │
│  └──────────────┘                        └──────────────┘       │
│                                               │                  │
│                                               ▼                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    ChromaDB 向量数据库                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ 法律法规     │  │ 判决书       │  │ 合同模板     │       │   │
│  │  │ (按款/项分段) │  │ (结构化分段) │  │ (条款分段)   │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. MMR 去重

### 2.1 目标

Maximal Marginal Relevance（MMR）算法减少检索结果中的冗余，提升多样性。

### 2.2 实现方案

在 `app/rag/retriever.py` 中添加 MMR 过滤：

```python
def mmr_rerank(
    query_embedding: list[float],
    candidates: list[dict],
    lambda_param: float = 0.5,
    top_k: int = 5,
) -> list[dict]:
    """MMR 去重：平衡相关性与多样性。

    lambda_param: 0 = 纯多样性, 1 = 纯相关性
    """
    selected = []
    remaining = candidates.copy()

    while len(selected) < top_k and remaining:
        best_score = -1
        best_idx = -1

        for i, cand in enumerate(remaining):
            # 相关性分数
            relevance = cand.get("score", 0)

            # 与已选结果的最大相似度
            max_sim = 0
            for sel in selected:
                sim = cosine_similarity(cand["embedding"], sel["embedding"])
                max_sim = max(max_sim, sim)

            # MMR 分数
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        if best_idx >= 0:
            selected.append(remaining.pop(best_idx))

    return selected
```

### 2.3 配置项

在 `app/core/config.py` 添加：

```python
# MMR 配置
MMR_LAMBDA: float = 0.5  # 0=纯多样性, 1=纯相关性
MMR_ENABLED: bool = True
```

---

## 3. 法条结构化分段

### 3.1 目标

按"款/项"级别分段，而非固定字符数分段，保持法条语义完整性。

### 3.2 分段策略

| 文档类型 | 分段规则 | 示例 |
|----------|----------|------|
| 法律法规 | 按"条"分段，长条按"款"拆分 | 第一千零四十三条 |
| 判决书 | 按"事实/理由/判决"分段 | 本院认为... |
| 合同 | 按"条款"分段 | 第一条 甲方义务... |

### 3.3 实现方案

在 `app/rag/document_loader.py` 添加法律专用分段器：

```python
import re

def split_legal_document(text: str, doc_type: str = "law") -> list[dict]:
    """法律文档结构化分段。"""
    chunks = []

    if doc_type == "law":
        # 按"第X条"分段
        pattern = r'(第[一二三四五六七八九十百千零\d]+[条章节])'
        parts = re.split(pattern, text)

        current_article = ""
        for i, part in enumerate(parts):
            if re.match(pattern, part):
                if current_article:
                    chunks.append({
                        "text": current_article.strip(),
                        "article": chunks[-1].get("article", "") if chunks else "",
                    })
                current_article = part
            else:
                current_article += part

        if current_article:
            chunks.append({"text": current_article.strip()})

    return chunks
```

---

## 4. 法律数据集入库

### 4.1 目标

下载并入库标准法律数据集，扩充知识库。

### 4.2 数据集

| 数据集 | 类型 | 规模 | 用途 |
|--------|------|------|------|
| SCL | 法条原文 | ~2 万部法律 | 知识库底库 |
| LeCaRD | 案例检索 | ~10 万裁判文书 | 检索评测 |

### 4.3 入库脚本

扩展 `scripts/ingest.py` 支持批量入库：

```bash
# 下载 SCL 数据集
HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py scl

# 入库 SCL
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py data/datasets/scl/

# 入库 LeCaRD
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py data/datasets/lecard/
```

---

## 5. 验证步骤

### 5.1 MMR 去重验证

```bash
# 测试查询（预期返回多样化结果）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py --hybrid --mmr "离婚相关法律"

# 对比不使用 MMR
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py --hybrid "离婚相关法律"
```

### 5.2 结构化分段验证

```bash
# 重新入库测试文档
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py --split-mode legal data/docs/

# 检索单条法条
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py "夫妻之间有什么义务"
```

### 5.3 数据集入库验证

```bash
# 检查入库数量
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python -c "
from app.rag.vector_store import VectorStore
vs = VectorStore()
print(f'入库文档数: {vs.collection.count()}')
"

# 检索测试
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py "故意杀人罪的处罚"
```

---

## 6. 阶段检查清单

- [x] `app/rag/retriever.py` MMR 去重算法
- [x] `app/core/config.py` MMR 配置项
- [x] `app/rag/document_loader.py` 法律专用分段器
- [x] `scripts/ingest.py` 支持法律分段模式
- [x] `scripts/download_dataset.py` 数据集下载脚本
- [x] SCL 数据集下载（twang2218/chinese-law-and-regulations）
- [x] LeCaRD 数据集下载（mteb/LeCaRDv2）
- [x] MMR 去重效果验证（已集成到 search_test.py）
- [x] 结构化分段效果验证（已集成到 ingest.py）
- [x] 文档更新（进度.md、开发指南.md）

---

## 7. 文件清单（Phase 8 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/rag/retriever.py` | 修改 | 添加 MMR 去重算法 |
| `app/core/config.py` | 修改 | 添加 MMR 配置项 |
| `app/rag/document_loader.py` | 修改 | 法律专用分段器 |
| `scripts/ingest.py` | 修改 | 支持法律分段模式 |
| `scripts/download_dataset.py` | 新建 | 数据集下载脚本 |
| `文档/phase8-检索优化.md` | 新建 | 本阶段实施指南 |
| `文档/进度.md` | 修改 | 更新 Phase 8 状态 |
| `文档/开发指南.md` | 修改 | 更新任务状态 |

---

**下一阶段预告：第九阶段——安全与异步（API 认证、请求限流、消息队列）。**
