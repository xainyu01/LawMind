"""数据库初始化脚本 — 建库建表 + 创建默认管理员."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def create_database():
    """创建数据库（如果不存在）。"""
    import pymysql

    # 从 MYSQL_URL 解析连接信息（不含数据库名）
    url = settings.MYSQL_URL
    # mysql+pymysql://root:1234@localhost:3306/legal_rag
    parts = url.replace("mysql+pymysql://", "").split("/")
    db_name = parts[-1] if len(parts) > 1 else "legal_rag"
    conn_parts = parts[0].split("@")
    user_pass = conn_parts[0].split(":")
    host_port = conn_parts[1].split(":")

    conn = pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]),
        user=user_pass[0],
        password=user_pass[1],
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"数据库 '{db_name}' 已就绪")
    finally:
        conn.close()


def create_tables():
    """创建所有表。"""
    from app.db.mysql_client import init_db
    init_db()
    print("所有表已创建")


def create_admin():
    """创建默认管理员账号。"""
    import bcrypt
    from sqlalchemy.orm import Session
    from app.db.mysql_client import SessionLocal
    from app.db.models import User

    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if existing:
            print(f"管理员 '{settings.ADMIN_USERNAME}' 已存在，跳过")
            return

        password_hash = bcrypt.hashpw(
            settings.ADMIN_PASSWORD.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

        admin = User(
            username=settings.ADMIN_USERNAME,
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"管理员 '{settings.ADMIN_USERNAME}' 创建成功")
    finally:
        db.close()


def main():
    print("=== 法律 RAG 系统 — 数据库初始化 ===")
    print(f"MySQL: {settings.MYSQL_URL}")
    print()

    create_database()
    create_tables()
    create_admin()

    print()
    print("初始化完成！")


if __name__ == "__main__":
    main()
