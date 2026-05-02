from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.database import get_db
from models.generation import Generation
from schemas.generation import GenerationListResponse, GenerationResponse

router = APIRouter(prefix="/api/generations", tags=["生图记录"])


@router.get("", response_model=GenerationListResponse)
def list_generations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取生图历史记录，分页"""
    total = db.query(Generation).count()
    items = (
        db.query(Generation)
        .order_by(desc(Generation.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return GenerationListResponse(
        total=total,
        items=[
            GenerationResponse(
                id=g.id,
                prompt=g.prompt,
                image_urls=g.image_urls or [],
                model=g.model,
                aspect_ratio=g.aspect_ratio,
                n_generated=g.n_generated,
                created_at=g.created_at,
            )
            for g in items
        ],
    )


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """获取统计数据（供 HomeView / AdminView 使用）"""
    total = db.query(Generation).count()
    return {
        "total_generations": total,
    }
