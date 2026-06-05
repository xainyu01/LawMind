# 法律 RAG 系统 — API 接口文档

> 基础地址：`http://localhost:8000`
> Swagger UI：`http://localhost:8000/docs`

---

## 1. 健康检查

**GET** `/health`

检查服务是否正常运行。

### 响应

```json
{
  "status": "ok"
}
```

---

## 2. 法律问答

**POST** `/api/v1/chat`

法律智能问答接口。流程：检索 → 重排序 → 过滤 → LLM 生成 → 返回答案与来源。

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户法律问题 |
| `session_id` | string | ❌ | 会话 ID，默认 `"default"`，用于多轮对话记忆 |
| `history` | array | ❌ | 历史对话（可选，当前由服务端记忆管理） |

### 请求示例

**基础查询：**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "夫妻之间有什么义务"}'
```

**带会话 ID（多轮对话）：**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "那离婚需要什么条件", "session_id": "user_123"}'
```

### 响应体

| 字段 | 类型 | 说明 |
|------|------|------|
| `answer` | string | LLM 生成的法律回答 |
| `sources` | array | 参考法条列表 |
| `intent` | string | 意图分类结果 |
| `cached` | bool | 是否命中语义缓存 |

### sources 元素结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 法条内容（截取前 300 字） |
| `source` | string | 来源文件名 |
| `score` | float | 相关性分数（rerank_score 或 rrf_score） |

### 响应示例

```json
{
  "answer": "根据《中华人民共和国民法典》第1043条，夫妻之间有以下义务：\n\n1. **互相忠实**——夫妻应当互相忠实，互相尊重。\n2. **互相扶养**——夫妻有互相扶养的义务。\n3. **共同抚养子女**——夫妻双方有抚养、教育和保护未成年子女的权利和义务。",
  "sources": [
    {
      "content": "第一千零四十三条 家庭应当树立优良家风，弘扬家庭美德，重视家庭文明建设。夫妻应当互相忠实，互相尊重，互相关爱；家庭成员应当敬老爱幼，互相帮助，维护平等、和睦、文明的婚姻家庭关系。",
      "source": "民法典节选.txt",
      "score": 0.9234
    }
  ],
  "intent": "statute_lookup",
  "cached": false
}
```

### 意图类型

| intent 值 | 说明 | 触发关键词 |
|-----------|------|------------|
| `statute_lookup` | 法条查询 | 第、条、法条、条文、规定、款 |
| `case_analysis` | 案例分析 | 案例、判决、裁定、判例、被告、原告 |
| `contract_review` | 合同审查 | 合同、审查、条款、违约、签订、协议 |
| `legal_qa` | 法律知识问答 | 默认 |
| `chitchat` | 闲聊 | 你好、你是谁（短文本） |

### 无结果响应

当知识库中未找到相关法条时：

```json
{
  "answer": "当前知识库中未找到与「xxx」相关的法律条文，无法给出有据可查的法律意见。建议您查阅相关法律法规原文或咨询专业律师。",
  "sources": [],
  "intent": "legal_qa",
  "cached": false
}
```

---

## 3. 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 422 | 请求参数验证失败 |
| 500 | 服务内部错误 |

---

## 4. 使用说明

### 启动服务

```bash
# FastAPI 服务
uv run python main.py

# 或 Streamlit 界面
HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
```

### 多轮对话

使用相同的 `session_id` 发送请求，系统会自动注入历史对话上下文：

```bash
# 第一轮
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是诉讼时效", "session_id": "session_001"}'

# 第二轮（会引用上一轮的上下文）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "普通诉讼时效是多久", "session_id": "session_001"}'
```

### 语义缓存

相同或高度相似的问题会命中缓存，`cached` 字段为 `true`，响应速度更快。

---

## 5. 内置交互文档

FastAPI 自动生成交互式 API 文档：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
