"""快速检索测试

用法:
    uv run python scripts/search_test.py "夫妻之间有什么义务"
    uv run python scripts/search_test.py --hybrid "离婚条件"
"""

import sys
from app.rag.vector_store import search
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker


def print_results(hits, title="检索结果"):
    for i, hit in enumerate(hits):
        score = hit.get("rerank_score") or hit.get("rrf_score") or hit.get("distance", "N/A")
        if isinstance(score, float):
            score = f"{score:.4f}"
        print(f"\n--- {i + 1} (score: {score}) ---")
        print(f"来源: {hit.get('metadata', {}).get('source', 'unknown')}")
        print(hit["content"][:300])


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--hybrid" in args or "-H" in args:
        args.remove("--hybrid") if "--hybrid" in args else args.remove("-H")
        query = args[0] if args else "夫妻之间有什么义务"
        print(f"=== 混合检索 (BM25 + 向量 + 重排序): {query} ===\n")

        retriever = get_retriever()
        reranker = get_reranker()

        candidates = retriever.search(query, top_k=10)
        print(f"--- 检索召回 {len(candidates)} 条 ---")

        reranked = reranker.rerank(query, candidates)
        print_results(reranked[:5], "重排序Top5")
    else:
        query = args[0] if args else "夫妻之间有什么义务"
        print(f"=== 向量检索: {query} ===\n")
        results = search(query, top_k=5)
        print_results(results)
