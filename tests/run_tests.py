"""
测试运行器

用法:
    PYTHONPATH=. uv run python tests/run_tests.py              # 运行所有单元测试
    PYTHONPATH=. uv run python tests/run_tests.py --unit       # 只运行单元测试
    PYTHONPATH=. uv run python tests/run_tests.py --functional  # 只运行功能测试
    PYTHONPATH=. uv run python tests/run_tests.py --all        # 运行所有测试
"""

import sys
import subprocess
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def run_unit_tests():
    """运行单元测试"""
    print("\n" + "=" * 60)
    print("运行单元测试 (pytest)")
    print("=" * 60 + "\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    return result.returncode == 0


def run_functional_tests():
    """运行功能测试"""
    print("\n" + "=" * 60)
    print("运行功能测试")
    print("=" * 60)

    tests = [
        ("向量检索", "tests/functional/test_vector_search.py"),
        ("混合检索", "tests/functional/test_hybrid_search.py"),
        ("重排序", "tests/functional/test_reranker.py"),
        ("性能基准", "tests/functional/test_performance.py"),
    ]

    passed = 0
    failed = 0

    for name, script in tests:
        print(f"\n--- {name} ---")
        result = subprocess.run(
            [sys.executable, script],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"功能测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return failed == 0


def print_manual_tests():
    """打印手动测试说明"""
    print("\n" + "=" * 60)
    print("需要手动测试的项目")
    print("=" * 60)
    print("""
以下测试需要人工操作:

1. Streamlit 界面测试
   启动: HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
   运行: PYTHONPATH=. uv run python tests/functional/test_streamlit.py
   - 登录页面
   - 聊天功能
   - 文件上传
   - 用户反馈
   - 管理员面板

2. API 接口测试 (需要先启动服务)
   启动: uv run python main.py
   运行: PYTHONPATH=. uv run python tests/functional/test_api.py
   - /health 健康检查
   - /auth 认证流程
   - /chat 问答接口
   - /metrics 指标接口
""")


def main():
    args = sys.argv[1:]

    if not args or "--unit" in args:
        run_unit_tests()

    if "--functional" in args or "--all" in args:
        run_functional_tests()

    if "--all" in args or "--manual" in args:
        print_manual_tests()

    if not args:
        print_manual_tests()


if __name__ == "__main__":
    main()
