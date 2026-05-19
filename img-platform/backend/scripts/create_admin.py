#!/usr/bin/env python3
"""创建初始管理员账号"""
import sys
sys.path.insert(0, '.')

from models.database import SessionLocal, init_db
from models.user import User
from core.security import hash_password


def create_admin(username: str = "admin", password: str = "admin123"):
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"用户 '{username}' 已存在，更新密码...")
            existing.password_hash = hash_password(password)
            existing.is_admin = True
        else:
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_admin=True,
            )
            db.add(user)
            print(f"创建管理员账号: {username} / {password}")
        db.commit()
        print("完成！")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
