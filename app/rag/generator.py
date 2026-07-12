from typing import List, Optional

from openai import OpenAI

from app.core.config import settings

LEGAL_SYSTEM_PROMPT = """你是一位专业的中国法律助手。你必须严格遵循以下规则：

1. 所有法律引用必须注明完整的法律名称和条文编号（例如："根据《中华人民共和国民法典》第1043条"）。
2. 只能引用下方「参考法条」中提供的法律条文内容。如果参考法条中没有相关内容，请如实说明"当前知识库中未找到相关法条"。
3. 不得编造、推测或引用不存在于参考法条中的法律条文。
4. 回答应条理清晰，先给出结论，再引用具体法条作为依据。
5. 如果问题涉及多个法律领域，请分别说明。"""

INTENT_CLASSIFY_PROMPT = """请判断用户问题的意图类型，只返回类型名称（statute_lookup / case_analysis / legal_qa / contract_review / chitchat）：
- statute_lookup: 查询具体法条、条文内容、法律条款
- case_analysis: 分析案例、判例、判决、裁定
- legal_qa: 法律知识问答、法律咨询
- contract_review: 合同审查、条款分析、协议问题
- chitchat: 闲聊、打招呼、问你是谁

用户问题：{query}
意图类型："""


def _build_context_text(contexts: List[dict]) -> str:
    """Build context block from retrieved documents for prompt injection."""
    parts = []
    for i, ctx in enumerate(contexts):
        source = ctx.get("metadata", {}).get("source", "未知来源")
        parts.append(f"[参考法条 {i + 1}] 来源: {source}\n{ctx['content']}")
    return "\n\n".join(parts)


def _classify_intent_with_llm(query: str) -> str:
    """Use LLM prompt for intent classification."""
    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "user", "content": INTENT_CLASSIFY_PROMPT.format(query=query)},
            ],
            temperature=0,
            max_tokens=20,
        )
        intent = response.choices[0].message.content.strip().lower()
        valid_intents = {"statute_lookup", "case_analysis", "legal_qa", "contract_review", "chitchat"}
        if intent in valid_intents:
            return intent
    except Exception:
        pass
    # Fallback to keyword-based classification
    return _classify_intent_keyword(query)


def _classify_intent_keyword(query: str) -> str:
    """Keyword-based intent classification as fallback."""
    q = query.strip()
    statute_keywords = ["第", "条", "法条", "条文", "规定", "款"]
    case_keywords = ["案例", "判决", "裁定", "判例", "胜诉", "败诉", "起诉", "被告", "原告"]
    contract_keywords = ["合同", "审查", "条款", "违约", "签订", "租赁", "买卖", "协议"]
    chitchat_keywords = ["你好", "你是谁", "你能干嘛", "谢谢", "再见"]

    if any(k in q for k in chitchat_keywords) and len(q) < 10:
        return "chitchat"
    if any(k in q for k in case_keywords):
        return "case_analysis"
    if any(k in q for k in contract_keywords):
        return "contract_review"
    if any(k in q for k in statute_keywords):
        return "statute_lookup"
    return "legal_qa"


CHITCHAT_RESPONSES = {
    "你好": "您好！我是法律RAG助手，可以帮您查询法律法规、分析案例、解答法律问题。请随时向我提问。",
    "你是谁": "我是基于RAG技术的法律智能助手，能够检索法律法规并给出有据可查的法律建议。",
    "你能干嘛": "我可以：1) 查询法律条文 2) 分析法律案例 3) 解答法律知识问题 4) 辅助合同审查。请告诉我您需要什么帮助？",
    "谢谢": "不客气！如有其他法律问题，随时问我。",
    "再见": "再见！祝您生活愉快，有法律问题随时联系。",
}


class LegalGenerator:
    """LLM generator wrapping DeepSeek API with legal-specific prompts."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    def generate(self, query: str, contexts: List[dict]) -> dict:
        """Generate legal answer with citations from retrieved contexts."""
        intent = _classify_intent_with_llm(query)

        if intent == "chitchat":
            for pattern, response in CHITCHAT_RESPONSES.items():
                if pattern in query:
                    return {"answer": response, "sources": [], "intent": intent}
            return {"answer": "您好！有什么法律问题需要我帮忙吗？", "sources": [], "intent": intent}

        # Build messages
        context_text = _build_context_text(contexts)
        user_message = f"【用户问题】\n{query}\n\n【参考法条】\n{context_text}\n\n请根据上述参考法条回答用户问题。"

        messages = [
            {"role": "system", "content": LEGAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

        answer = response.choices[0].message.content

        # Build sources list from contexts
        sources = []
        for ctx in contexts:
            sources.append({
                "content": ctx["content"][:300],
                "source": ctx.get("metadata", {}).get("source", "未知"),
                "score": ctx.get("rerank_score") or ctx.get("rrf_score") or ctx.get("distance"),
            })

        return {"answer": answer, "sources": sources, "intent": intent}

    def generate_stream(self, query: str, contexts: List[dict]):
        """流式生成，逐 token yield（仅非闲聊意图）."""
        intent = _classify_intent_with_llm(query)

        if intent == "chitchat":
            for pattern, response in CHITCHAT_RESPONSES.items():
                if pattern in query:
                    yield {"token": response, "sources": [], "intent": intent, "done": True}
                    return
            yield {"token": "您好！有什么法律问题需要我帮忙吗？", "sources": [], "intent": intent, "done": True}
            return

        context_text = _build_context_text(contexts)
        user_message = f"【用户问题】\n{query}\n\n【参考法条】\n{context_text}\n\n请根据上述参考法条回答用户问题。"

        messages = [
            {"role": "system", "content": LEGAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # Build sources upfront
        sources = []
        for ctx in contexts:
            sources.append({
                "content": ctx["content"][:300],
                "source": ctx.get("metadata", {}).get("source", "未知"),
                "score": ctx.get("rerank_score") or ctx.get("rrf_score") or ctx.get("distance"),
            })

        stream = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield {"token": chunk.choices[0].delta.content, "done": False}

        yield {"token": "", "sources": sources, "intent": intent, "done": True}


_generator: Optional[LegalGenerator] = None


def get_generator() -> LegalGenerator:
    global _generator
    if _generator is None:
        _generator = LegalGenerator()
    return _generator
