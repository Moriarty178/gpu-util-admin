from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

import gpu_core
from app.db.session import check_db
from app.deps import ScopeDep, SessionDep, get_engine
from app.schemas.analytics import MetaOut
from app.schemas.common import HealthOut, Problem
from app.services import analytics_service

log = logging.getLogger(__name__)
router = APIRouter(tags=["meta"])


@router.get(
    "/healthz",
    response_model=HealthOut,
    summary="Kiểm tra kết nối CSDL và phiên bản gpu_core",
    responses={503: {"model": Problem, "description": "Không kết nối được CSDL"}},
)
def healthz(engine: Annotated[Engine, Depends(get_engine)]) -> HealthOut:
    try:
        check_db(engine)
    except SQLAlchemyError as exc:
        log.error("healthz: lỗi CSDL: %s", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Không kết nối được CSDL.") from exc
    return HealthOut(db="ok", gpu_core=gpu_core.__version__)


@router.get(
    "/meta",
    response_model=MetaOut,
    summary="Khoảng dữ liệu, các kỳ (lô VTNet đã nhập), giá trị bộ lọc (đầu mối, model GPU, cụm), cài đặt",
)
def meta(s: SessionDep, scope: ScopeDep) -> MetaOut:
    return MetaOut.model_validate(analytics_service.meta(s, scope))
