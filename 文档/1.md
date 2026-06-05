我们用 `uv` 来替代 pip + venv 的组合，管理更简单、速度也更快。  
下面是修改后的第一阶段（替换原来的虚拟环境部分，其他目录结构、`.env`、代码文件不变）。

---

## 第一阶段：环境准备 & 项目骨架搭建（使用 uv）

### 1. 安装 uv
如果你的环境还没有 uv，先安装：
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或者用 pip 安装
pip install uv

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
安装完成后重新打开终端，检查版本：
```bash
uv --version
```

### 2. 创建项目并初始化 uv
```bash
uv init legal-rag
cd legal-rag
```
这会自动生成 `pyproject.toml`、`.gitignore`、`.python-version` 等文件。

创建我们自己的子目录：
```bash
mkdir -p app/api app/core app/rag app/db models data/docs data/chroma
```

### 3. 添加项目依赖
用 `uv add` 一次性添加所有依赖，uv 会自动处理虚拟环境（`.venv`）和锁文件：
```bash
uv add fastapi==0.115.0 uvicorn[standard]==0.30.6 python-multipart==0.0.9 \
  langchain==0.3.7 langchain-community==0.3.5 langchain-text-splitters==0.3.1 \
  chromadb==0.5.5 unstructured[pdf,docx]==0.15.4 python-docx==1.1.2 pypdf2==3.0.1 \
  sentence-transformers==3.1.1 openai==1.51.0 python-dotenv==1.0.1 \
  redis==5.1.1 bm25s==0.6.1
```
> `uv add` 会自动创建虚拟环境（`.venv`）、更新 `pyproject.toml` 和 `uv.lock`，不需要手动 `source activate`。

### 4. 配置环境变量
项目根目录创建 `.env` 文件（内容同前）：
```ini
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh
```
`.gitignore` 中 uv 已经默认排除了 `.env`，无需额外修改。

### 5. 写最小 FastAPI 入口
创建 `main.py`：
```python
import uvicorn
from fastapi import FastAPI

app = FastAPI(title="法律RAG系统", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

### 6. 验证：启动服务
使用 uv 运行入口文件（自动使用项目虚拟环境）：
```bash
uv run python main.py
```
浏览器访问 `http://localhost:8000/health`，看到 `{"status":"ok"}` 即成功。

### 7. 下载本地嵌入模型（只需一次）
新建 `scripts/download_model.py`：
```python
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv

load_dotenv()
model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh")
model = SentenceTransformer(model_name, cache_folder="./models")
print(f"模型已下载到: ./models/{model_name}")
```
通过 uv 运行：
```bash
uv run python scripts/download_model.py
```
下载完成后 `models/` 目录下会多出一个 `bge-small-zh` 文件夹。

### 8. 完成
此时项目结构如下（uv 生成的文件已包含在内）：
```
legal-rag/
├── .venv/                 # uv 自动管理的虚拟环境
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── main.py
├── .env
├── app/
│   ├── api/
│   ├── core/
│   ├── rag/
│   └── db/
├── models/
│   └── bge-small-zh/
├── data/
│   ├── docs/
│   └── chroma/
└── scripts/
    └── download_model.py
```
之后运行任何脚本都使用 `uv run python <file>`，不用手动激活虚拟环境。

---

## ✅ 第一阶段完成标志
- 项目由 `uv` 管理，依赖安装无报错
- `uv run python main.py` 正常启动 FastAPI
- `/health` 返回 ok
- 嵌入模型已下载至 `models/` 目录

**下一步：第二阶段——法律文档解析与向量化入库。**  
准备好后说"继续第二阶段"。
