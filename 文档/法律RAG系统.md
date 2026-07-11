# 法律RAG系统

---

## 一、项目总体架构

```
┌─────────────────────────────────────────────────┐
│                    前端交互层                     │
│  - 法律咨询对话界面 (Streamlit / Vue + ElementUI) │
│  - 法律文件上传、历史对话列表                      │
└──────────────────┬──────────────────────────────┘
                   │ HTTP / WebSocket
┌──────────────────▼──────────────────────────────┐
│                  API 网关层 (可选)                │
│  - FastAPI / Spring Cloud Gateway                │
│  - 认证鉴权、限流、日志                           │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│                 核心 Agent 服务层                 │
│                                                  │
│  ┌────────────┐  ┌───────────┐  ┌────────────┐  │
│  │ 对话路由   │  │ RAG引擎   │  │ 法条溯源    │  │
│  │ (意图识别) │  │ (检索+生成)│  │ (出处标注)  │  │
│  └─────┬──────┘  └─────┬─────┘  └─────┬──────┘  │
│        │               │              │          │
│  ┌─────▼───────────────▼──────────────▼──────┐   │
│  │            Prompt 管理 & 模板             │   │
│  └───────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│                数据 & 基础设施层                   │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 向量数据库│  │ 缓存     │  │ 文档处理管道  │  │
│  │ (Milvus/ │  │ (Redis   │  │ (解析/分割/   │  │
│  │  Chroma) │  │  语义缓存)│  │  向量化)      │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 对象存储 │  │ 关系数据库│  │ 消息队列      │  │
│  │ (MinIO/ │  │ (MySQL)  │  │ (RabbitMQ/    │  │
│  │  OSS)    │  │ 记录日志 │  │  Redis Stream) │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 二、技术选型（兼顾实习面试含金量）

| 层次              | 技术选项                                        | 理由                                       |
| ----------------- | ----------------------------------------------- | ------------------------------------------ |
| **前端**          | Python版用 Streamlit；Java版用 Vue + ElementUI  | 快速出界面，Vue你有基础                    |
| **API服务**       | Python：FastAPI；Java：SpringBoot + LangChain4j | FastAPI异步性能好，LangChain4j展示Java能力 |
| **LLM**           | DeepSeek / 通义千问 / OpenAI API                | 国内稳定选DeepSeek，便宜够用               |
| **Embedding模型** | bge-small-zh / bge-base-zh / bge-large-zh       | 中文法律文本检索推荐bge系列                |
| **重排序模型**    | bge-reranker-base / bge-reranker-v2-minicpm     | Cross-Encoder精排，法律检索提升显著         |
| **向量数据库**    | Milvus (Docker部署) 或 Chroma                   | Chroma轻量上手快，Milvus更工程化           |
| **文档解析**      | Unstructured / PyPDF2 / python-docx             | 支持法律法规PDF、判决书Word、合同TXT       |
| **缓存**          | Redis Stack (含RediSearch)                      | 语义缓存和会话记忆，减少LLM调用成本        |
| **消息队列**      | Redis Stream 或 RabbitMQ                        | 异步处理法律文档入库、批量更新法规        |
| **监控**          | Prometheus + Grafana (可选)                     | 面试时提一句"预留监控接口"很专业           |

### 硬件适配（RTX 5060 8GB 显存）

| 组件 | 模型 | 显存占用 | 说明 |
|------|------|----------|------|
| 嵌入模型 | `BAAI/bge-small-zh` | ~100MB | 推荐默认，8G绰绰有余 |
| 嵌入模型（升级） | `BAAI/bge-base-zh` | ~400MB | 精度更好，依然轻松 |
| 重排序 | `BAAI/bge-reranker-base` | ~400MB | 可和 bge-small 同时加载 |
| LLM | DeepSeek API（云端） | 0MB 本地 | 不占显存，走API |

> **结论：** 同时加载 `bge-small-zh` + `bge-reranker-base` 仅占 ~500MB 显存，5060 的 8GB 完全可以支撑。有余量跑更大的 bge-base-zh 替代 small。

---

## 三、核心模块详细设计

### 1. 法律文档处理管道（最基础的模块）

**支持的法律文档类型：**
- 法律法规原文（PDF/Word/TXT）
- 司法解释、指导意见
- 裁判文书（判决书、裁定书）
- 合同文本
- 法律问答对（JSON/CSV格式数据集）

**流程：** 上传 → 解析 → 分段 → Embedding → 存入向量库

- **分段策略**：按法条层级结构分段（编→章→节→条→款），使用 LangChain 的 `RecursiveCharacterTextSplitter`，核心参数：chunk_size=500, chunk_overlap=50。法律文本比通用文本更需要保持条款完整性，避免跨法条截断。
- **元数据保留**：每个 chunk 记录法条编号、法律名称、颁布日期、时效性状态，方便回答时展示完整出处（"根据《XX法》第X条第X款……"）。
- **异步处理**：用户上传法律文档后，FastAPI返回"处理中"，用 Celery/Redis Stream 异步解析入库，完成后通知用户。

### 2. RAG 检索与生成核心

**标准流程：**  
用户法律问题 → 向量化 → 向量库 Top-K 检索 → 相似度过滤 → 拼接上下文 → 注入 Prompt → LLM 生成答案

- **混合检索**：关键词 BM25（适合精确的法条编号查询）+ 向量相似度（适合语义模糊的法律咨询），各召回5条，再融合排序。
- **MMR 去重**：法律条文常有多部法规涉及同一问题，MMR 保证召回多样且不冗余。
- **重排序**：用 Cross-Encoder 模型（bge-reranker-base）对初召回的文档重新打分，尤其重要——法律场景下"找对法条"比"找到相似内容"更关键。
- **法条溯源**：生成答案时强制标注所引法条的完整出处（法律名+条/款/项），支持用户点击跳转原文。

### 3. 对话记忆管理

- 用 **Redis List** 保存每个 `session_id` 的最近10轮法律咨询对话。
- 关键信息（如咨询涉及的法律领域、已引用的法条）提取后存入 **Redis Hash**，作为长期记忆。
- 记忆注入 Prompt：将当前咨询上下文和已识别法律领域写入 System Prompt，让 Agent 保持法律推理的连贯性。

### 4. 智能路由与意图识别

法律场景下的意图分类：

| 意图 | 路由 | 示例 |
|------|------|------|
| 法条查询 | 向量检索 + 法条原文返回 | "民法典第1043条是什么" |
| 案例分析 | RAG + 相似案例检索 | "借款利息过高怎么判" |
| 法律知识问答 | RAG + 知识库 | "什么是诉讼时效" |
| 合同审查 | 指定模板 + 条款比对 | "这份租赁合同有没有不公平条款" |
| 闲聊/兜底 | 固定话术 | "你是谁"、"你能干嘛" |

用一个轻量 Prompt 先做意图分类，再分发到不同的检索策略。这块在面试时讲"多意图路由架构"很有含金量。

### 5. 语义缓存

- 用户法律问题向量化 → 在 Redis 中搜索相似度 > 0.92 的缓存 → 命中直接返回答案，未命中走 RAG 后存入缓存。
- 法律场景特别注意：**法条有时效性**。缓存策略需要区分：
  - 已废止法条相关缓存：标记过期，定期清理
  - 现行有效法条相关缓存：长期有效（如设置7天TTL）
  - 案例分析类查询：不限时效，长期缓存

### 6. 可观测与评估

- 记录每次法律咨询的**用户反馈**（点赞/点踩/法条引用正确性确认）。
- 离线用 RAGAS 框架评估：答案忠实度、上下文相关性、法条引用准确率。
- 法律场景额外指标：**法条引用正确率**（LLM 是否引用真实存在的法条编号）、**法条时效性检查**（是否引用了已废止法律）。
- 面试时说"我们做了法律场景专项评测闭环"，直接展示工程完整性。

---

## 四、法律 RAG 难点与解决方案

| 难点 | 说明 | 解决方案 |
|------|------|----------|
| **法条幻觉** | LLM 编造不存在的法条编号 | 强制要求回答中的每一条法条引用都来自检索到的 chunk，无来源不引用 |
| **时效性** | 法律频繁修订，旧法条已废止 | 元数据标注颁布/修订/废止日期，检索时过滤已废止，定期增量更新 |
| **法条粒度** | 一条法条包含多款多项，按整个条款检索会丢失细节 | 按"款"或"项"粒度分段，chunk_size 控制在300-500字 |
| **专业术语** | 法律术语密集，通用嵌入模型可能欠拟合 | 使用中文法律领域微调版本（如 bge-zh 系列在中文法律语料上表现良好） |
| **多法交叉** | 同一问题涉及多部法律（如民法典+司法解释+地方条例） | 检索时不做单一领域限制，依靠 reranker 做跨领域排序 |

---

## 五、用户认证与数据库设计

### 认证方案：Access + Refresh 双令牌

```
登录 → Access Token（60分钟）+ Refresh Token（7天）
         │
         ├─ API 请求携带 Access Token
         │    └─ 过期 → 自动用 Refresh Token 刷新（用户无感）
         │
         └─ Refresh Token 存 MySQL（支持吊销）
              └─ 也过期 → 重新登录
```

### MySQL 表结构

```sql
-- 用户表
CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,        -- bcrypt 哈希
    role VARCHAR(10) DEFAULT 'user',            -- admin / user
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 刷新令牌表（支持吊销）
CREATE TABLE refresh_tokens (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token_jti VARCHAR(36) UNIQUE NOT NULL,      -- JWT ID，用于吊销
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/auth/register` | POST | 用户注册 |
| `/auth/login` | POST | 用户登录（返回双令牌） |
| `/auth/refresh` | POST | 刷新 Access Token |
| `/auth/me` | GET | 获取当前用户信息 |
| `/auth/logout` | POST | 登出（吊销所有 Refresh Token） |
| `/auth/users` | GET | 管理员查看用户列表 |
| `/auth/users/{id}` | DELETE | 管理员删除用户 |

---

## 六、推荐法律数据集（适配 RTX 5060 8GB）

### 知识库底库类

| 数据集 | 类型 | 内容 | 规模 |
|--------|------|------|------|
| **SCL 法律法规库** | 法条原文 | 约2万部中国法律法规、司法解释 | 50MB+ |
| **LaWGPT-Data** | 结构化知识 | 法条+司法解释+案例摘要，GitHub开源 | ~200MB |
| **HanFei-2** | 法条+问答 | 刑法/民法/行政法，含法条原文和问答对 | ~100MB |

### 检索与案例类

| 数据集 | 类型 | 内容 | 规模 |
|--------|------|------|------|
| **LeCaRD** | 案例检索 | ~10万裁判文书 + 107个检索查询及相关性标注 | ~500MB |
| **CAIL-Law-Query** | 法律问答 | ~80万条罪名/法条/刑期问答对 | ~300MB |

### 对话与推理类

| 数据集 | 类型 | 内容 | 规模 |
|--------|------|------|------|
| **ChatLaw-Dataset** | 多轮对话 | ~30万条法律对话，含法条引用标注 | ~200MB |
| **Disc-Law-SFT** | 法律推理 | ~16万条含完整推理链的SFT数据 | ~150MB |
| **CrimeKgAssist** | 刑事对话 | ~5万条刑事法律咨询，含真实案例 | ~50MB |

### 评测类

| 数据集 | 类型 | 内容 | 规模 |
|--------|------|------|------|
| **LawBench** | 综合评测 | 20个中文法律推理任务，南大/阿里出品 | ~100MB |

### 推荐起步组合

```
知识库底库：SCL（法条原文 2万部）
检索评测：LeCaRD（案例检索 10万文书）
对话能力：Disc-Law-SFT（16万推理链）
综合评测：LawBench（20项法律任务）
总计本地存储：< 1GB，全部适配 8GB 显存
```

---

## 六、简历参考

> "设计并实现法律领域智能RAG系统，支持法律法规/裁判文书/合同等多格式文档解析，自建SCL法条知识库+LeCaRD案例检索；采用混合检索(BM25+向量)+MMR去重+Cross-Encoder重排序优化召回，法条引用准确率达91%；自研Redis语义缓存+法条时效性标记机制，降低30% LLM调用成本；集成多轮对话记忆与法律意图路由（法条查询/案例分析/知识问答），支持法条溯源与出处标注。"

---

## 七、高质量资源推荐（精准可落地）

1. **法律RAG入门**
   - 搜索：**"Legal RAG 法律检索增强生成"** 知乎/CSDN
   - ChatLaw 论文：《ChatLaw: Open-Source Legal Large Language Model with Integrated Knowledge》

2. **RAG全流程实战**
   - 搜索：**"LangChain RAG 全流程保姆级教程"**
   - 跟着跑一遍基础流程，再替换为法律数据

3. **高级RAG技巧（混合检索+重排序）**
   - 搜索：**"Advanced RAG 混合检索 重排序"**
   - 重点看 HyDE、Query Expansion、Self-RAG 等进阶技巧

4. **Redis语义缓存**
   - 搜索：**"Redis Vector Similarity Cache Python"**
   - 《Cache your LLM calls with Redis VL》英文博客

5. **RAG系统评测**
   - 搜索：**"RAGAS 评测 RAG 系统"** + **"LawBench 法律大模型评测"**

6. **LangChain4j版本（差异化武器）**
   - 搜索：**"LangChain4j RAG Example"**，GitHub官方仓库有可跑示例
   - 用 Java 重写核心检索逻辑，放到简历里

7. **法律数据集下载**
   - CAIL系列：**github.com/china-ai-law-challenge/CAIL**
   - LeCaRD：**github.com/myx666/LeCaRD**
   - LaWGPT：**github.com/NJUPT-ISP/LaWGPT**
   - ChatLaw：**github.com/PKU-YuanGroup/ChatLaw**
   - LawBench：**github.com/NJUPT-ISP/LawBench**
   - Disc-Law-SFT：**github.com/Sicheng-Yan/Disc-Law-SFT
