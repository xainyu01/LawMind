"""对话记忆管理 — 近期对话（List）+ 上下文提取（Hash）."""

import json
import logging
from typing import List, Optional

from app.core.config import settings
from app.db.backend import get_backend

logger = logging.getLogger(__name__)


class ConversationMemory:
    """管理会话级对话记忆和长期上下文提取."""

    def __init__(self):
        self._backend = get_backend()

    def _msg_key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def _ctx_key(self, session_id: str) -> str:
        return f"session:{session_id}:context"

    def save_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        intent: str = "",
        sources: Optional[list] = None,
    ) -> None:
        """保存一轮对话（user + assistant）到 List，并更新上下文 Hash."""
        import time

        user_entry = json.dumps({"role": "user", "content": user_msg}, ensure_ascii=False)
        asst_entry = json.dumps({"role": "assistant", "content": assistant_msg}, ensure_ascii=False)

        key = self._msg_key(session_id)
        self._backend.lpush(key, asst_entry, user_entry)
        # 保留最近 N 轮（每轮 2 条消息）
        self._backend.ltrim(key, 0, settings.MAX_MEMORY_TURNS * 2 - 1)
        self._backend.expire(key, settings.SESSION_TTL)

        # 更新上下文
        self._update_context(session_id, user_msg, intent, sources or [])

    def _update_context(
        self, session_id: str, query: str, intent: str, sources: list
    ) -> None:
        """从本轮对话中提取关键信息并更新上下文 Hash."""
        key = self._ctx_key(session_id)
        ctx = self._backend.hgetall(key)

        # 累加法律领域（从 sources 的 metadata 中提取）
        domains = set(ctx.get("law_domains", "").split(", ")) if ctx.get("law_domains") else set()
        for src in sources:
            meta = src.get("metadata", {})
            domain = meta.get("law_domain", "")
            if domain:
                domains.add(domain)
        if domains:
            ctx["law_domains"] = ", ".join(sorted(domains))

        # 累加引用法条
        cited = set(ctx.get("cited_statutes", "").split(", ")) if ctx.get("cited_statutes") else set()
        for src in sources:
            statute = src.get("metadata", {}).get("statute", "")
            if statute:
                cited.add(statute)
        if cited:
            ctx["cited_statutes"] = ", ".join(sorted(cited))

        # 更新最近意图
        if intent:
            ctx["last_intent"] = intent

        # 保存用户陈述的关键事实（简单取 query 前 200 字）
        facts = ctx.get("user_facts", "")
        new_fact = query[:200]
        if facts:
            ctx["user_facts"] = f"{facts}\n{new_fact}"
        else:
            ctx["user_facts"] = new_fact

        self._backend.hset(key, ctx)
        self._backend.expire(key, settings.SESSION_TTL)

    def get_history(self, session_id: str, last_n: Optional[int] = None) -> List[dict]:
        """获取最近 N 轮对话历史."""
        if last_n is None:
            last_n = settings.MAX_MEMORY_TURNS
        key = self._msg_key(session_id)
        raw = self._backend.lrange(key, 0, last_n * 2 - 1)
        messages = []
        for item in reversed(raw):  # lrange 返回最新在前，反转为时间顺序
            try:
                messages.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        return messages

    def get_context_for_prompt(self, session_id: str) -> str:
        """生成注入 LLM 的上下文摘要文本."""
        history = self.get_history(session_id, last_n=5)
        ctx = self._backend.hgetall(self._ctx_key(session_id))

        parts = []

        if history:
            parts.append("对话历史:")
            for msg in history:
                role = "用户" if msg["role"] == "user" else "助手"
                content = msg["content"][:300]
                parts.append(f"  {role}: {content}")

        if ctx:
            parts.append("\n关键信息:")
            if ctx.get("law_domains"):
                parts.append(f"  - 法律领域: {ctx['law_domains']}")
            if ctx.get("cited_statutes"):
                parts.append(f"  - 已引用法条: {ctx['cited_statutes']}")
            if ctx.get("user_facts"):
                # 只取最近 3 条事实
                facts = ctx["user_facts"].split("\n")[-3:]
                parts.append(f"  - 用户关键事实: {'; '.join(facts)}")

        return "\n".join(parts) if parts else ""
