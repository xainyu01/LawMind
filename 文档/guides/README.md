# 开发与部署指南

> [← 返回索引](../README.md)

---

## 指南文档

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [开发指南](./开发指南.md) | 快速开始、目录结构、常用命令、注意事项 | 日常开发 |
| [部署指南](./部署指南.md) | Docker 部署、Nginx 配置、生产环境 | 上线部署 |
| [进度](./进度.md) | 各阶段完成状态、待办事项 | 项目管理 |

---

## 快速开始

```bash
# 1. 初始化数据库
uv run python scripts/init_db.py

# 2. 启动 FastAPI
uv run python main.py

# 3. 启动 Streamlit
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
```

---

## 相关文档

- [Phase 文档](../phase/README.md) — 各阶段详细实施指南
- [项目介绍](../architecture/项目介绍.md) — 项目概述与技术栈
- [法律RAG系统](../architecture/法律RAG系统.md) — 架构设计
