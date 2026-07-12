"""
功能测试 - 性能基准

测试检索和嵌入性能。
运行方式: PYTHONPATH=. uv run python tests/functional/test_performance.py
"""

import time
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def test_embedding_performance():
    """测试嵌入性能"""
    from app.rag.embedding import BgeEmbedding

    print("=" * 60)
    print("性能基准测试")
    print("=" * 60)

    print("\n[1] 嵌入模型加载")
    start = time.time()
    embedder = BgeEmbedding()
    load_time = time.time() - start
    print(f"    加载耗时: {load_time:.1f}s")

    print("\n[2] 单条嵌入")
    start = time.time()
    for _ in range(10):
        embedder.embed_query("测试文本")
    avg = (time.time() - start) / 10
    print(f"    平均耗时: {avg*1000:.1f}ms")

    print("\n[3] 批量嵌入 (batch=512)")
    texts = ["测试文本" + str(i) for i in range(512)]
    start = time.time()
    embedder.embed_documents(texts, batch_size=512)
    elapsed = time.time() - start
    print(f"    512条耗时: {elapsed:.1f}s")
    print(f"    吞吐量: {512/elapsed:.0f} 条/秒")


def test_vector_search_performance():
    """测试向量检索性能"""
    from app.rag.vector_store import search

    print("\n[4] 向量检索性能")
    # 预热
    search("预热", top_k=1)

    queries = ["夫妻义务", "离婚条件", "故意杀人", "合同违约", "正当防卫"]
    times = []
    for q in queries:
        start = time.time()
        search(q, top_k=5)
        times.append(time.time() - start)

    avg = sum(times) / len(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    print(f"    查询数: {len(queries)}")
    print(f"    平均耗时: {avg*1000:.1f}ms")
    print(f"    P95耗时: {p95*1000:.1f}ms")
    print(f"    最慢: {max(times)*1000:.1f}ms")
    print(f"    最快: {min(times)*1000:.1f}ms")

    assert avg < 0.5, f"平均响应过慢: {avg:.3f}s"
    print("    PASS (avg < 500ms)")


def test_hybrid_search_performance():
    """测试混合检索性能"""
    from app.rag.retriever import get_retriever

    print("\n[5] 混合检索性能")
    retriever = get_retriever()

    # 首次（构建索引）
    print("    构建 BM25 索引中...")
    start = time.time()
    retriever.search("预热", top_k=1)
    build_time = time.time() - start
    print(f"    索引构建耗时: {build_time:.1f}s")

    # 后续查询
    queries = ["夫妻义务", "离婚条件", "故意杀人"]
    times = []
    for q in queries:
        start = time.time()
        retriever.search(q, top_k=5)
        times.append(time.time() - start)

    avg = sum(times) / len(times)
    print(f"    后续查询平均: {avg*1000:.1f}ms")
    print("    PASS")


def main():
    test_embedding_performance()
    test_vector_search_performance()
    test_hybrid_search_performance()

    print("\n" + "=" * 60)
    print("性能测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
