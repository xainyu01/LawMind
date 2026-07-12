"""
功能测试 - Streamlit 界面（手动测试清单）

此脚本输出 Streamlit 手动测试步骤，需人工验证。
运行方式: PYTHONPATH=. uv run python tests/functional/test_streamlit.py
"""


def print_manual_tests():
    """打印手动测试清单"""
    print("=" * 60)
    print("Streamlit 界面手动测试清单")
    print("=" * 60)
    print()
    print("启动命令:")
    print("  HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py")
    print()
    print("-" * 60)

    tests = [
        {
            "name": "1. 登录页面",
            "steps": [
                "打开 http://localhost:8501",
                "确认显示登录界面（非直接进入聊天）",
                "输入 admin / admin123 点击登录",
                "确认登录成功，进入聊天界面",
            ],
            "expected": "登录成功后进入主聊天界面",
        },
        {
            "name": "2. 注册功能",
            "steps": [
                "点击注册标签",
                "输入新用户名和密码（至少6位）",
                "点击注册",
                "确认注册成功并自动登录",
            ],
            "expected": "新用户注册成功",
        },
        {
            "name": "3. 聊天功能",
            "steps": [
                "在输入框输入 '夫妻之间有什么义务'",
                "点击发送",
                "确认返回法条引用",
                "确认显示来源信息",
            ],
            "expected": "返回《民法典》第1043条相关内容",
        },
        {
            "name": "4. 文件上传",
            "steps": [
                "展开侧边栏",
                "点击 '上传法律文档'",
                "上传一个 TXT 文件（如民法典节选）",
                "确认显示 '入库成功' 提示",
            ],
            "expected": "文件成功入库到 ChromaDB",
        },
        {
            "name": "5. 用户反馈",
            "steps": [
                "发送一个问题获得回答后",
                "点击 '赞' 按钮",
                "检查 data/feedback.jsonl 是否有新记录",
            ],
            "expected": "feedback.jsonl 记录了反馈",
        },
        {
            "name": "6. 管理员面板",
            "steps": [
                "以 admin 登录",
                "展开侧边栏的 '管理员面板'",
                "确认显示用户列表",
            ],
            "expected": "显示所有注册用户",
        },
    ]

    for test in tests:
        print(f"\n{test['name']}")
        print("-" * 40)
        print("步骤:")
        for i, step in enumerate(test["steps"], 1):
            print(f"  {i}. {step}")
        print(f"预期: {test['expected']}")
        print("结果: [ ] 通过  [ ] 失败")

    print("\n" + "=" * 60)
    print("手动测试完成后，请记录结果")
    print("=" * 60)


if __name__ == "__main__":
    print_manual_tests()
