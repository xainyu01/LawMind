# 法律 RAG 系统 — 文档索引

> 最后更新：2026-07-12

---

## 文档结构

```
文档/
├── README.md                ← 你在这里
├── phase/                   # 开发阶段文档（Phase 1-10）
├── guides/                  # 开发与部署指南
├── architecture/            # 系统架构设计
├── qa/                      # 知识问答
├── issues/                  # 问题记录与工作报告
├── prompts/                 # 提示词模板
├── planning/                # 未来规划
└── archive/                 # 历史归档
```

---

## 快速导航

### 新手上路

| 文档 | 说明 |
|------|------|
| [项目介绍](./architecture/项目介绍.md) | 项目概述、核心功能、技术栈、使用示例 |
| [开发指南](./guides/开发指南.md) | 快速开始、常用命令、注意事项 |
| [部署指南](./guides/部署指南.md) | Docker 部署、Nginx 配置、生产环境 |
| [进度](./guides/进度.md) | 各阶段完成状态、待办事项 |

### 架构设计

| 文档 | 说明 |
|------|------|
| [法律RAG系统](./architecture/法律RAG系统.md) | 完整架构设计、模块规格、数据集推荐 |
| [架构对比](./architecture/架构对比.md) | 技术选型对比分析 |
| [智能客服RAG](./architecture/智能客服RAG.md) | 原始设计文档（已归档参考） |

### 开发阶段

| 阶段 | 文档 | 状态 |
|------|------|------|
| Phase 1 | [环境搭建](./phase/phase1-环境搭建.md) | ✅ |
| Phase 2 | [文档解析与向量化](./phase/phase2-文档解析与向量化.md) | ✅ |
| Phase 2 补充 | [教学讲解](./phase/phase2-教学讲解.md) | ✅ |
| Phase 3 | [检索与生成](./phase/phase3-检索与生成.md) | ✅ |
| Phase 4 | [对话记忆与缓存](./phase/phase4-对话记忆与缓存.md) | ✅ |
| Phase 5 | [前端与评估](./phase/phase5-前端与评估.md) | ✅ |
| Phase 6 | [高级功能](./phase/phase6-高级功能.md) | ✅ |
| Phase 7 | [生产部署](./phase/phase7-生产部署.md) | ✅ |
| Phase 8 | [检索优化](./phase/phase8-检索优化.md) | ✅ |
| Phase 9 | [安全与异步](./phase/phase9-安全与异步.md) | ✅ |
| Phase 10 | [完善与优化](./phase/phase10-完善与优化.md) | ✅ |

### 知识库

| 文档 | 说明 |
|------|------|
| [数据格式与分片问答](./qa/数据格式与分片问答.md) | Parquet、分片逻辑、ChromaDB、HNSW、BM25 等问答 |

### 问题与报告

| 文档 | 说明 |
|------|------|
| [2026-07-12 工作报告](./issues/2026-07-12_工作报告.md) | 最新工作报告 |
| [ChromaDB 索引损坏问题](./issues/2026-07-12_ChromaDB索引损坏与数据完整性问题.md) | HNSW 索引损坏、修复方案 |
| [历史问题记录](./issues/问题记录.md) | 历史问题记录 |

### 规划与改进

| 文档 | 说明 |
|------|------|
| [未来改进方向](./planning/未来改进方向.md) | 图片 PDF OCR、模型升级、知识图谱等 |

### 提示词

| 文档 | 说明 |
|------|------|
| [问题修复上下文](./prompts/问题修复上下文.md) | 问题修复的标准提示词模板 |

---

## 按主题查找

### 检索相关

- [数据格式与分片问答](./qa/数据格式与分片问答.md) — BM25、向量检索、RRF 融合、HNSW 索引
- [Phase 3 检索与生成](./phase/phase3-检索与生成.md) — 混合检索实现
- [Phase 8 检索优化](./phase/phase8-检索优化.md) — MMR 去重、法条结构化分段
- [法律RAG系统](./architecture/法律RAG系统.md) — 检索架构设计

### 认证与安全

- [Phase 9 安全与异步](./phase/phase9-安全与异步.md) — API 认证、限流、消息队列
- [Phase 10 完善与优化](./phase/phase10-完善与优化.md) — MySQL 用户认证、双令牌
- [开发指南](./guides/开发指南.md) — 认证相关命令

### 部署相关

- [部署指南](./guides/部署指南.md) — Docker、Nginx、CI/CD
- [Phase 7 生产部署](./phase/phase7-生产部署.md) — 容器化实施

### 数据处理

- [数据格式与分片问答](./qa/数据格式与分片问答.md) — Parquet 格式、文档读取、分片逻辑
- [Phase 2 文档解析与向量化](./phase/phase2-文档解析与向量化.md) — 文档解析实现
- [Phase 8 检索优化](./phase/phase8-检索优化.md) — 法律结构化分段
