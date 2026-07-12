"""Phase 3 一键验证脚本

用法:
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/verify_phase3.py
"""

import sys
import io

# Windows 终端中文兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def check(ok, msg):
    print(f"  {'[OK]' if ok else '[FAIL]'} {msg}")
    if not ok:
        print("\n验证失败，请检查上述错误。")
        sys.exit(1)
    return ok


print("=" * 50)
print("Phase 3 验证：RAG 检索与 LLM 生成")
print("=" * 50)

# 1. 配置
print("\n[1/5] 配置检查...")
from app.core.config import settings  # noqa: E402

check(settings.RERANKER_MODEL_NAME == "BAAI/bge-reranker-base", f"重排序模型: {settings.RERANKER_MODEL_NAME}")
check(settings.BM25_TOP_K == 10, f"BM25_TOP_K: {settings.BM25_TOP_K}")
check(settings.LLM_MODEL != "", f"LLM 模型: {settings.LLM_MODEL}")

# 2. 混合检索
print("\n[2/5] 混合检索 (BM25 + 向量 + RRF)...")
from app.rag.retriever import get_retriever  # noqa: E402

retriever = get_retriever()
results = retriever.search("夫妻义务", top_k=3)
check(len(results) >= 1, f"召回 {len(results)} 条结果")
if results:
    print(f"       Top1 [rrf={results[0].get('rrf_score', 0):.4f}]: {results[0]['content'][:60]}...")

# 3. 重排序
print("\n[3/5] 重排序 (Cross-Encoder)...")
from app.rag.reranker import get_reranker  # noqa: E402

reranker = get_reranker()
reranked = reranker.rerank("夫妻义务", results)
check(len(reranked) >= 1, f"重排序 {len(reranked)} 条")
if reranked:
    print(f"       Top1 [rerank={reranked[0].get('rerank_score', 0):.4f}]: {reranked[0]['content'][:60]}...")

# 4. LLM 生成
print("\n[4/5] LLM 生成 (DeepSeek API)...")
from app.rag.generator import get_generator  # noqa: E402

generator = get_generator()
result = generator.generate("夫妻义务", reranked[:3])
check("answer" in result and len(result["answer"]) > 10, f"生成回答 ({len(result['answer'])} 字)")
check(result.get("intent") in ("legal_qa", "statute_lookup"), f"意图: {result.get('intent')}")
check(len(result.get("sources", [])) >= 1, f"来源数: {len(result.get('sources', []))}")
print(f"       回答摘要: {result['answer'][:120]}...")

# 5. GPU 显存
print("\n[5/5] GPU 显存检查...")
try:
    import torch

    if torch.cuda.is_available():
        used = torch.cuda.memory_allocated() / 1024**2
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        check(used < 8000, f"显存占用: {used:.0f} MB / {total:.1f} GB (RTX 5060)")
    else:
        check(False, "CUDA 不可用，请检查 PyTorch 安装")
except Exception as e:
    check(False, f"GPU 检测异常: {e}")

print("\n" + "=" * 50)
print("[OK] Phase 3 验证全部通过！")
print("=" * 50)
