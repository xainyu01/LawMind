# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

**语言要求：在此项目中必须全程使用中文回复用户。**

**GPU 约束：任何涉及 GPU 的操作（模型训练、模型加载到 GPU、CUDA 相关配置修改、大批量 GPU 推理、下载新模型等）必须先向用户二次确认，得到明确许可后方可执行。仅读取 GPU 状态（如 `nvidia-smi`、查询显存占用）无需确认。**

**Phase Plan 规则：每个阶段（Phase）必须有对应的 plan 文件 `文档/phaseN-<阶段名>.md`，参照已有 phase 文档的风格编写（包含架构概览、模块设计、核心接口、验证步骤、阶段检查清单、文件清单）。完成当前阶段任务后，必须更新当前 phase 文档的状态，并创建下一个 phase 的 plan 文件。**

## 项目概述

法律领域 RAG（检索增强生成）系统。支持多格式法律文档解析（PDF/Word/TXT 格式的法律法规、判决书、合同），混合检索（BM25 + 向量相似度 + Cross-Encoder 重排序），多轮对话记忆，语义缓存，意图路由，以及法条溯源。

## 包管理

本项目使用 **uv**（`/c/Users/Admin/Desktop/RAG/.venv`）。始终通过 uv 运行 Python，不要直接用系统 Python。

```bash
uv run python <script.py>        # 在 venv 中运行脚本
uv add <package>                 # 添加依赖
uv sync                          # 同步 venv 到 lockfile
```

## 构建、运行、测试

```bash
# 启动 Streamlit 聊天界面（推荐）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py

# 启动 FastAPI 开发服务器
uv run python main.py            # 监听 http://localhost:8000

# 健康检查
curl http://localhost:8000/health

# 对话接口测试（启动服务后）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"夫妻之间有什么义务"}'

# 入库法律文档（需要 PYTHONPATH 和 HF_ENDPOINT）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py data/docs/

# 向量检索测试
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py "查询内容"

# 混合检索测试（BM25 + 向量 + 重排序）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/search_test.py --hybrid "查询内容"
```

> `HF_ENDPOINT` 在加载嵌入/重排序模型时必须设置（sentence-transformers 检查 HF）。`PYTHONPATH=.` 用于脚本从 `app/` 导入模块。

暂无自动化测试套件，验证靠手动执行上述命令。

## 技术栈

| 领域              | 选型                                         |
| ----------------- | -------------------------------------------- |
| Web 框架          | FastAPI 0.115 + Uvicorn 0.30                 |
| LLM 提供商        | DeepSeek（通过 `openai` SDK，OpenAI 兼容接口） |
| 嵌入模型          | BAAI/bge-small-zh（`sentence-transformers` 本地加载） |
| 重排序模型        | BAAI/bge-reranker-base（Cross-Encoder 本地加载） |
| 向量数据库        | ChromaDB 1.5                                |
| 文档解析          | Unstructured, PyPDF2, python-docx            |
| 文本分割          | LangChain `RecursiveCharacterTextSplitter`   |
| 关键词检索        | bm25s                                        |
| 缓存 / 记忆       | Redis 5.1                                    |
| LLM 编排          | LangChain 1.3 + langchain-community          |

关键版本锁定在 `pyproject.toml` 中。Python >= 3.14 必须。

**重要：** PyTorch 必须从 CUDA 12.8 索引安装，不能使用默认 PyPI 镜像。`pyproject.toml` 通过以下配置强制：

```toml
[tool.uv.sources]
torch = { index = "pytorch-cu128" }
```

请勿删除此配置，否则 `uv lock` 会解析为 CPU 版本。

## 硬件

目标 GPU：**RTX 5060 8GB 显存**。嵌入模型（`bge-small-zh`，~100MB）和重排序模型（`bge-reranker-base`，~400MB）在本地运行，合计占用不到 1GB 显存。LLM 通过 DeepSeek API（云端）运行，不占本地显存。

## 法律数据集

推荐的法律知识库数据集（详见 `文档/法律RAG系统.md` 第 5 节）：

| 数据集 | 类型 | 用途 |
|--------|------|------|
| SCL | 法条原文 | 知识库底库（~2 万部法律） |
| LeCaRD | 案例检索 | 检索评测（~10 万裁判文书） |
| Disc-Law-SFT | 法律推理 | 对话能力（160K 样本） |
| LawBench | 综合评测 | 多任务评测（20 项任务） |

## 环境变量

通过 `python-dotenv` 从 `.env` 加载。`.env` 文件必须包含：

- `DEEPSEEK_API_KEY` — DeepSeek API 密钥
- `DEEPSEEK_BASE_URL` — DeepSeek 接口地址（默认 `https://api.deepseek.com`）
- `LLM_MODEL` — 模型名称（默认 `deepseek-chat`）
- `EMBEDDING_MODEL_NAME` — 嵌入模型（默认 `BAAI/bge-small-zh`）
- `HF_ENDPOINT` — HuggingFace 镜像（默认 `https://hf-mirror.com`，国内下载模型必须）

## 架构

计划模块布局（来自 `文档/1.md`），对应 `app/` 目录结构：

```
app/
├── api/
│   └── routes.py     # /chat 问答接口，编排检索→重排序→生成管线
├── core/
│   └── config.py     # 统一配置（含 Reranker/Retriever/LLM/Redis 参数）
├── rag/
│   ├── document_loader.py  # PDF/Word/TXT 文档加载与分段
│   ├── embedding.py        # BGE 嵌入模型封装（GPU 推理）
│   ├── vector_store.py     # ChromaDB 增删查
│   ├── retriever.py        # BM25 + 向量混合检索，RRF 融合（Phase 3）
│   ├── reranker.py         # Cross-Encoder 重排序（Phase 3）
│   └── generator.py        # DeepSeek LLM + 法律 Prompt + 意图分类（Phase 3）
└── db/               # Redis 会话/缓存管理（Phase 4 预留）
models/               # 本地下载的嵌入 & 重排序模型
data/
├── docs/             # 用户上传的法律文档
├── chroma/           # ChromaDB 持久化数据
└── eval/             # 评测数据集与结果
scripts/              # 一次性工具脚本
```

核心 RAG 流程：上传 → 解析（Unstructured/PyPDF2/python-docx）→ 分割（RecursiveCharacterTextSplitter，chunk_size=500，适配法律条款）→ 嵌入（BGE）→ 存储（ChromaDB）。检索采用混合 BM25 + 向量相似度，配合 Cross-Encoder 重排序和 MMR 去重。

会话记忆使用 Redis List（最近 N 轮对话）+ Redis Hash（提取的关键事实、涉及的法律领域）。语义缓存在调用 LLM 前检查 Redis 中相似度 > 0.92 的历史问题，根据法条时效性区分 TTL。

意图路由覆盖：法条查询、案例分析、法律知识问答、合同审查、闲聊兜底。

## 设计文档

- `文档/法律RAG系统.md` — 完整架构设计、技术决策、模块规格、数据集推荐、简历参考
- `文档/phase1-环境搭建.md` — 第一阶段实施指南（uv 配置、依赖安装、项目骨架）✅
- `文档/phase2-文档解析与向量化.md` — 第二阶段实施指南（文档解析、嵌入、ChromaDB 入库）✅
- `文档/phase3-检索与生成.md` — 第三阶段实施指南（混合检索、重排序、LLM 生成、/chat 接口）✅
- `文档/phase4-对话记忆与缓存.md` — 第四阶段实施指南（对话记忆、语义缓存）✅
- `文档/phase5-前端与评估.md` — 第五阶段实施指南（RAGAS 评测、文件上传、用户反馈）🔧
- `文档/进度.md` — 全部阶段进度跟踪与检查清单
- `文档/开发指南.md` — 下次继续开发必读
- `文档/智能客服RAG.md` — 原智能客服设计（已归档）
