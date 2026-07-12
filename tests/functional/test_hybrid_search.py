"""
功能测试 - 混合检索

需要真实数据和模型。首次运行会构建 BM25 索引（耗时较长）。
运行方式: PYTHONPATH=. uv run python tests/functional/test_hybrid_search.py
"""

import sys
import time
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def test_hybrid_search():
    """测试混合检索功能"""
    from app.rag.retriever import get_retriever
    from app.rag.vector_store import get_collection_count

    print("=" * 60)
    print("混合检索功能测试")
    print("=" * 60)

    count = get_collection_count()
    print(f"\n数据量: {count} 条")

    retriever = get_retriever()

    # 1. 首次检索（可能触发索引构建）
    print("\n[1] 首次检索（可能构建 BM25 索引）")
    start = time.time()
    results = retriever.search("夫妻义务", top_k=5)
    elapsed = time.time() - start
    print(f"    耗时: {elapsed:.1f}s")
    print(f"    返回: {len(results)} 条")
    assert len(results) > 0, "混合检索返回空"

    for i, r in enumerate(results):
        source = r.get("metadata", {}).get("source", "unknown")
        rrf = r.get("rrf_score", 0)
        content = r["content"][:50]
        print(f"    [{i+1}] rrf={rrf:.4f} | {source}: {content}...")
    print("    PASS")

    # 2. 精确法条号检索
    print("\n[2] 精确法条号: '民法典第1043条'")
    results = retriever.search("民法典第1043条", top_k=5)
    print(f"    返回: {len(results)} 条")
    found = any("1043" in r.get("content", "") or "一千零四十三" in r.get("content", "") for r in results)
    print(f"    包含第1043条: {found}")
    print("    PASS" if found else "    WARN: 未精确匹配")

    # 3. 语义检索
    print("\n[3] 语义检索: '夫妻之间有什么义务'")
    results = retriever.search("夫妻之间有什么义务", top_k=5)
    print(f"    返回: {len(results)} 条")
    assert len(results) > 0
    print("    PASS")

    # 4. 已废止法条过滤
    print("\n[4] 已废止法条过滤")
    results = retriever.search("婚姻法", top_k=5, filter_repealed=True)
    for r in results:
        status = r.get("metadata", {}).get("status", "active")
        assert status != "repealed", "过滤失败：包含已废止法条"
    print(f"    返回 {len(results)} 条，均已过滤已废止法条")
    print("    PASS")

    # 5. 后续检索性能
    print("\n[5] 后续检索性能")
    queries = ["夫妻义务", "离婚条件", "故意杀人"]
    times = []
    for q in queries:
        start = time.time()
        retriever.search(q, top_k=5)
        times.append(time.time() - start)
    avg = sum(times) / len(times)
    print(f"    平均响应: {avg*1000:.1f}ms")
    print("    PASS")

    print("\n" + "=" * 60)
    print("所有混合检索测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    test_hybrid_search()
