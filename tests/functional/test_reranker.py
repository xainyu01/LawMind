"""
功能测试 - 重排序模块

需要真实重排序模型。
运行方式: PYTHONPATH=. uv run python tests/functional/test_reranker.py
"""

import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def test_reranker():
    """测试重排序功能"""
    from app.rag.reranker import get_reranker

    print("=" * 60)
    print("重排序功能测试")
    print("=" * 60)

    reranker = get_reranker()

    # 1. 基本重排序
    print("\n[1] 基本重排序")
    candidates = [
        {"content": "夫妻应当互相忠实，互相尊重，互相关爱。", "metadata": {"source": "民法典"}},
        {"content": "故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑。", "metadata": {"source": "刑法"}},
        {"content": "夫妻有互相扶养的义务。", "metadata": {"source": "民法典"}},
    ]
    query = "夫妻之间的义务"
    result = reranker.rerank(query, candidates)
    assert len(result) == 3
    assert "rerank_score" in result[0]
    # 相关的应该排在前面
    print(f"    Top-1: {result[0]['content'][:40]}... (score={result[0]['rerank_score']:.4f})")
    print(f"    Top-2: {result[1]['content'][:40]}... (score={result[1]['rerank_score']:.4f})")
    print(f"    Top-3: {result[2]['content'][:40]}... (score={result[2]['rerank_score']:.4f})")
    # 民法典相关内容应该排在刑法前面
    assert result[0]["metadata"]["source"] == "民法典"
    print("    PASS")

    # 2. 空候选列表
    print("\n[2] 空候选列表")
    result = reranker.rerank("测试", [])
    assert result == []
    print("    PASS")

    # 3. 单个候选
    print("\n[3] 单个候选")
    result = reranker.rerank("测试", [{"content": "测试内容", "metadata": {}}])
    assert len(result) == 1
    print("    PASS")

    print("\n" + "=" * 60)
    print("所有重排序测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    test_reranker()
