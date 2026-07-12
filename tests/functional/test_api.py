"""
功能测试 - API 接口

需要启动 FastAPI 服务。
运行方式:
  1. 先启动服务: uv run python main.py
  2. 再运行测试: PYTHONPATH=. uv run python tests/functional/test_api.py
"""

import sys

try:
    import requests
except ImportError:
    print("需要安装 requests: uv add requests")
    sys.exit(1)

BASE_URL = "http://localhost:8000"


def test_health():
    """测试健康检查"""
    print("\n[1] 健康检查 GET /health")
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print(f"    {data}")
    print("    PASS")


def test_auth_flow():
    """测试认证流程（注册→登录→获取用户信息）"""
    print("\n[2] 认证流程")

    # 注册
    print("    [2.1] 注册")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "username": "test_user",
        "password": "test123456",
    }, timeout=10)
    if resp.status_code == 409:
        print("    用户已存在，跳过注册")
    else:
        assert resp.status_code == 200, f"注册失败: {resp.text}"
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        print("    注册成功，获得 token")

    # 登录
    print("    [2.2] 登录")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "admin",
        "password": "admin123",
    }, timeout=10)
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()
    access_token = data["access_token"]
    _refresh_token = data["refresh_token"]
    print("    登录成功")

    # 获取用户信息
    print("    [2.3] 获取用户信息")
    resp = requests.get(f"{BASE_URL}/auth/me", headers={
        "Authorization": f"Bearer {access_token}",
    }, timeout=10)
    assert resp.status_code == 200
    user_info = resp.json()
    assert user_info["username"] == "admin"
    assert user_info["role"] == "admin"
    print(f"    用户: {user_info['username']}, 角色: {user_info['role']}")
    print("    PASS")

    return access_token


def test_chat(token: str):
    """测试 /chat 接口"""
    print("\n[3] /chat 接口")
    headers = {"Authorization": f"Bearer {token}"}

    test_cases = [
        ("夫妻之间有什么义务", "statute_lookup", "民法典"),
        ("离婚需要什么条件", "statute_lookup", None),
    ]

    for query, expected_intent, expected_content in test_cases:
        print(f"\n    [3.x] 查询: '{query}'")
        resp = requests.post(f"{BASE_URL}/api/v1/chat", json={
            "query": query,
            "session_id": "test",
        }, headers=headers, timeout=30)
        assert resp.status_code == 200, f"请求失败: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert "sources" in data
        assert "intent" in data
        print(f"    意图: {data['intent']}")
        print(f"    来源: {len(data['sources'])} 条")
        print(f"    回答: {data['answer'][:80]}...")
        if expected_content:
            if expected_content in data["answer"]:
                print(f"    包含 '{expected_content}': YES")
            else:
                print(f"    WARN: 回答中未包含 '{expected_content}'")

    print("\n    PASS")


def test_unauthorized():
    """测试未认证访问"""
    print("\n[4] 未认证访问")
    resp = requests.post(f"{BASE_URL}/api/v1/chat", json={
        "query": "测试",
    }, timeout=10)
    assert resp.status_code == 401
    print(f"    状态码: {resp.status_code} (预期 401)")
    print("    PASS")


def test_metrics(token: str):
    """测试 Prometheus 指标"""
    print("\n[5] Prometheus 指标 GET /api/v1/metrics")
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/api/v1/metrics", headers=headers, timeout=10)
    assert resp.status_code == 200
    assert "rag_requests_total" in resp.text
    print("    指标内容包含 rag_requests_total")
    print("    PASS")


def main():
    print("=" * 60)
    print("API 接口功能测试")
    print("=" * 60)
    print(f"目标: {BASE_URL}")

    try:
        test_health()
        token = test_auth_flow()
        test_unauthorized()
        test_chat(token)
        test_metrics(token)

        print("\n" + "=" * 60)
        print("所有 API 测试通过!")
        print("=" * 60)
    except requests.ConnectionError:
        print(f"\n无法连接到 {BASE_URL}")
        print("请先启动服务: uv run python main.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
