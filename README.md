# 法律 RAG 系统

基于检索增强生成（RAG）的法律智能问答系统，支持法条查询、案例分析、法律知识问答、合同审查。

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

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd RAG

# 安装依赖
uv sync
```

### 2. 配置环境变量

复制并编辑 `.env` 文件：

```bash
# DeepSeek API
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# HuggingFace 镜像（国内必须）
HF_ENDPOINT=https://hf-mirror.com

# MySQL
MYSQL_URL=mysql+pymysql://root:1234@localhost:3306/legal_rag

# JWT 密钥（生产环境请修改）
JWT_ACCESS_SECRET=your-access-secret-key
JWT_REFRESH_SECRET=your-refresh-secret-key

# 默认管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```

### 3. 初始化数据库

```bash
# 创建数据库、表结构、默认管理员
uv run python scripts/init_db.py
```

### 4. 下载并入库法律数据集

```bash
# 下载 SCL 法律法规数据集（~153MB）
HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py scl

# 下载 LeCaRD 案例检索数据集（~151MB）
HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py lecard

# 入库 SCL 数据集（法律结构化分段）
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py --split-mode legal data/datasets/scl/

# 入库自定义法律文档
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest.py data/docs/
```

### 5. 启动服务

```bash
# 终端 1：启动 FastAPI 后端
uv run python main.py
# → http://localhost:8000

# 终端 2：启动 Streamlit 前端
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
# → http://localhost:8501
```

### 6. 使用系统

1. 浏览器打开 `http://localhost:8501`
2. 默认管理员账号：`admin` / `admin123`
3. 也可注册新账号
4. 登录后即可开始法律问答

---

## API 接口

### 认证接口

| 接口 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/auth/register` | POST | 无 | 用户注册 |
| `/auth/login` | POST | 无 | 用户登录（返回双令牌） |
| `/auth/refresh` | POST | 无 | 刷新 Access Token |
| `/auth/me` | GET | JWT | 获取当前用户信息 |
| `/auth/logout` | POST | JWT | 登出（吊销所有 Refresh Token） |
| `/auth/users` | GET | JWT+Admin | 查看所有用户 |
| `/auth/users/{id}` | DELETE | JWT+Admin | 删除用户 |

### 业务接口

| 接口 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/v1/chat` | POST | JWT | 法律问答 |
| `/api/v1/chat/async` | POST | JWT | 异步问答（任务队列） |
| `/api/v1/task/{id}` | GET | JWT | 查询异步任务结果 |
| `/health` | GET | 无 | 健康检查 |
| `/metrics` | GET | 无 | Prometheus 指标 |

### 请求示例

```bash
# 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# 法律问答
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"夫妻之间有什么义务"}'
```

---

## Docker 部署

```bash
# 构建并启动所有服务
docker-compose up -d

# 服务访问
# - Streamlit 界面：http://localhost:8501
# - FastAPI 文档：http://localhost:8000/docs
# - Nginx 代理：http://localhost:80
```

---

## 评测

```bash
# 运行 RAGAS 风格评测
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py

# 详细输出
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py --verbose
```

评测指标：
- **Faithfulness**（忠实度）：答案是否被上下文支持
- **Answer Relevancy**（相关性）：答案与问题的相关程度
- **Context Precision**（精确度）：检索上下文中相关比例
- **Context Recall**（召回率）：标准答案被上下文覆盖比例

---

## 目录结构

```
RAG/
├── main.py                          # FastAPI 入口
├── app.py                           # Streamlit 聊天界面
├── pyproject.toml                   # 项目配置
├── Dockerfile                       # Docker 配置
├── docker-compose.yml               # 多容器编排
├── nginx.conf                       # Nginx 配置
│
├── app/
│   ├── api/
│   │   ├── routes.py                # /chat 问答接口
│   │   └── auth_routes.py           # /auth 认证接口
│   ├── core/
│   │   ├── config.py                # 统一配置
│   │   ├── auth.py                  # 双令牌认证（Access + Refresh）
│   │   ├── logging.py               # 结构化日志
│   │   └── rate_limit.py            # 滑动窗口限流
│   ├── db/
│   │   ├── backend.py               # Redis + DiskCache 双后端
│   │   ├── memory.py                # 对话记忆
│   │   ├── cache.py                 # 语义缓存
│   │   ├── queue.py                 # Redis Stream 任务队列
│   │   ├── mysql_client.py          # SQLAlchemy 引擎
│   │   └── models.py                # User + RefreshToken 模型
│   └── rag/
│       ├── document_loader.py       # 文档解析（法律结构化分段）
│       ├── embedding.py             # BGE 嵌入模型
│       ├── vector_store.py          # ChromaDB 向量存储
│       ├── retriever.py             # BM25 + 向量混合检索
│       ├── reranker.py              # Cross-Encoder 重排序
│       └── generator.py             # DeepSeek LLM 生成
│
├── scripts/
│   ├── init_db.py                   # 数据库初始化
│   ├── ingest.py                    # 文档入库
│   ├── search_test.py               # 检索测试
│   ├── eval_ragas.py                # RAGAS 评测
│   ├── download_dataset.py          # 数据集下载
│   └── worker.py                    # 后台 Worker
│
├── data/
│   ├── docs/                        # 法律文档
│   ├── chroma/                      # ChromaDB 持久化
│   ├── cache/                       # DiskCache
│   ├── eval/                        # 评测数据
│   └── datasets/                    # 法律数据集
│       ├── scl/                     # SCL 法律法规
│       └── lecard/                  # LeCaRD 案例检索
│
└── 文档/                            # 项目文档
    ├── 进度.md                      # 进度跟踪
    ├── 开发指南.md                  # 开发必读
    ├── 法律RAG系统.md               # 架构设计
    └── 项目介绍.md                  # 详细项目介绍
```

---

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | - | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名称 |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-zh` | 嵌入模型 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像 |
| `MYSQL_URL` | `mysql+pymysql://root:1234@localhost:3306/legal_rag` | MySQL 连接 |
| `JWT_ACCESS_SECRET` | - | Access Token 密钥 |
| `JWT_REFRESH_SECRET` | - | Refresh Token 密钥 |
| `JWT_ACCESS_EXPIRE_MINUTES` | `60` | Access Token 有效期 |
| `JWT_REFRESH_EXPIRE_DAYS` | `7` | Refresh Token 有效期 |
| `ADMIN_USERNAME` | `admin` | 默认管理员用户名 |
| `ADMIN_PASSWORD` | `admin123` | 默认管理员密码 |
| `REDIS_URL` | `redis://localhost:6379` | Redis 连接 |
| `AUTH_ENABLED` | `true` | 是否启用认证 |
| `RATE_LIMIT_ENABLED` | `false` | 是否启用限流 |
