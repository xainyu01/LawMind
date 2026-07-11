# 法律 RAG 系统

基于检索增强生成的法律智能问答系统，支持法条查询、案例分析、法律知识问答、合同审查。

## 技术栈

| 层次 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 前端 | Streamlit |
| LLM | DeepSeek API（云端） |
| 嵌入模型 | BAAI/bge-small-zh（本地 GPU） |
| 重排序 | BAAI/bge-reranker-base（本地 GPU） |
| 向量数据库 | ChromaDB |
| 关键词检索 | bm25s + jieba |
| 关系数据库 | MySQL 8.0 |
| 缓存/会话 | Redis / DiskCache |
| 认证 | JWT（Access + Refresh 双令牌） |

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 初始化 MySQL 数据库
uv run python scripts/init_db.py

# 3. 启动 FastAPI 服务
uv run python main.py

# 4. 启动 Streamlit 界面（需要 FastAPI 运行中）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
```

## 目录结构

```
app/
├── api/
│   ├── routes.py                # /chat 问答接口
│   └── auth_routes.py           # /auth 认证接口
├── core/
│   ├── config.py                # 统一配置
│   ├── auth.py                  # 双令牌认证
│   ├── logging.py               # 结构化日志
│   └── rate_limit.py            # 限流中间件
├── db/
│   ├── backend.py               # Redis + DiskCache
│   ├── memory.py                # 对话记忆
│   ├── cache.py                 # 语义缓存
│   ├── queue.py                 # Redis Stream 任务队列
│   ├── mysql_client.py          # SQLAlchemy
│   └── models.py                # ORM 模型
└── rag/
    ├── document_loader.py       # 文档解析
    ├── embedding.py             # 嵌入模型
    ├── vector_store.py          # ChromaDB
    ├── retriever.py             # 混合检索
    ├── reranker.py              # 重排序
    └── generator.py             # LLM 生成

scripts/
├── init_db.py                   # 数据库初始化
├── ingest.py                    # 文档入库
├── search_test.py               # 检索测试
├── eval_ragas.py                # 评测脚本
├── download_dataset.py          # 数据集下载
└── worker.py                    # 后台 Worker

data/
├── docs/                        # 法律文档
├── chroma/                      # ChromaDB 持久化
├── cache/                       # DiskCache
├── eval/                        # 评测数据
└── datasets/                    # 法律数据集
```

## API 接口

| 接口 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/auth/register` | POST | 无 | 用户注册 |
| `/auth/login` | POST | 无 | 用户登录 |
| `/auth/refresh` | POST | 无 | 刷新 Token |
| `/auth/me` | GET | JWT | 当前用户信息 |
| `/auth/logout` | POST | JWT | 登出 |
| `/api/v1/chat` | POST | JWT | 问答接口 |
| `/api/v1/chat/async` | POST | JWT | 异步问答 |
| `/api/v1/task/{id}` | GET | JWT | 查询异步结果 |
| `/health` | GET | 无 | 健康检查 |
| `/metrics` | GET | 无 | Prometheus 指标 |

## 环境变量

```bash
# LLM
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# 模型
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh
HF_ENDPOINT=https://hf-mirror.com

# MySQL
MYSQL_URL=mysql+pymysql://root:1234@localhost:3306/legal_rag

# JWT
JWT_ACCESS_SECRET=your-access-secret
JWT_REFRESH_SECRET=your-refresh-secret

# 默认管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```
