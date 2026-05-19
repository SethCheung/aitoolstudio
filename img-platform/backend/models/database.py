import os

from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./img_platform.db")

if DATABASE_URL.startswith("sqlite:///") and DATABASE_URL != "sqlite:///:memory:":
    sqlite_path = DATABASE_URL.removeprefix("sqlite:///")
    sqlite_dir = os.path.dirname(sqlite_path)
    if sqlite_dir:
        os.makedirs(sqlite_dir, exist_ok=True)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}  # SQLite 需要
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# 基础模型类，包含公共字段
class BaseModel(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


def init_db():
    """初始化数据库，创建所有表，执行兼容迁移"""
    Base.metadata.create_all(bind=engine)

    # 迁移: canvas_documents 加 conversation_id（安全幂等）
    _migrate_canvas_documents_conversation_id()


def _migrate_canvas_documents_conversation_id():
    """给 canvas_documents 补 conversation_id 列，SQLite 安全幂等"""
    import sqlite3
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(canvas_documents)")
        columns = [row[1] for row in cur.fetchall()]
        if "conversation_id" not in columns:
            cur.execute("ALTER TABLE canvas_documents ADD COLUMN conversation_id INTEGER")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_canvas_documents_conversation_id "
                "ON canvas_documents(conversation_id)"
            )
            conn.commit()
    except Exception:
        pass  # 表不存在等情况，create_all 会处理
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_db():
    """获取数据库会话的依赖注入函数"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
