"""
功能测试 - 向量检索

需要真实 ChromaDB 数据和嵌入模型。
运行方式: PYTHONPATH=. uv run python tests/functional/test_vector_search.py
"""

import sys
import time
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def test_vector_search():
    """测试向量检索基本功能"""
    from app.rag.vector_store import search, get_collection_count

    print("=" * 60)
    print("向量检索功能测试")
    print("=" * 60)

    # 1. 检查数据量
    count = get_collection_count()
    print(f"\n[1] 数据量检查: {count} 条")
    assert count > 100000, f"数据量不足: {count}"
    print("    PASS")

    # 2. 基本检索
    print("\n[2] 基本检索: '夫妻义务'")
    start = time.time()
    results = search("夫妻义务", top_k=5)
    elapsed = time.time() - start
    print(f"    耗时: {elapsed:.3f}s")
    print(f"    返回: {len(results)} 条")
    assert len(results) > 0, "检索返回空结果"
    for i, r in enumerate(results):
        source = r["metadata"].get("source", "unknown")
        content = r["content"][:60]
        print(f"    [{i+1}] {source}: {content}...")
    print("    PASS")

    # 3. 带 where 过滤的检索
    print("\n[3] 带 where 过滤的检索")
    results_filtered = search("夫妻义务", top_k=5, where={"status": {"$ne": "repealed"}})
    print(f"    返回: {len(results_filtered)} 条")
    for r in results_filtered:
        assert r["metadata"].get("status") != "repealed", "过滤失败：包含已废止法条"
    print("    PASS")

    # 4. 多查询测试
    print("\n[4] 多查询测试")
    test_cases = [
        ("离婚条件", "民法典"),
        ("故意杀人", "刑法"),
        ("合同违约", "民法典"),
    ]
    for query, expected_source in test_cases:
        results = search(query, top_k=3)
        print(f"    '{query}' -> {len(results)} 条")
        assert len(results) > 0, f"'{query}' 返回空"

    print("    PASS")

    # 5. 性能测试
    print("\n[5] 性能测试")
    queries = ["夫妻义务", "离婚条件", "故意杀人", "合同违约"]
    times = []
    search("预热", top_k=1)  # 预热
    for q in queries:
        start = time.time()
        search(q, top_k=5)
        times.append(time.time() - start)
    avg = sum(times) / len(times)
    print(f"    平均响应: {avg*1000:.1f}ms")
    assert avg < 0.5, f"平均响应过慢: {avg:.3f}s"
    print("    PASS")

    print("\n" + "=" * 60)
    print("所有向量检索测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    test_vector_search()
