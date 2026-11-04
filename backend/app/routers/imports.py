"""/imports — nhập file VTNet / thống kê theo lô (PLAN §5, §7). Router mỏng: mọi logic ở import_service."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.db.models import ImportBatch
from app.deps import EngineDep, SessionDep, SettingsDep, UserDep
from app.errors import ServiceError
from app.repo import batch_repo, settings_repo
from app.schemas.common import Problem
from app.schemas.imports import BatchListOut, BatchOut
from app.scope import CurrentUser
from app.services import auth_service, import_service
from app.services.analytics_service import warm_up

router = APIRouter(prefix="/imports", tags=["imports"])
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _warm_after_change(request: Request, engine: EngineDep, bg: BackgroundTasks) -> None:
    """Dữ liệu đổi → đọc sẵn lại cho phân tích (chạy nền sau khi đã trả response)."""
    if request.app.state.settings.warm_cache:
        bg.add_task(warm_up, engine, request.app.state.analytics_cache)


def _audit(s: SessionDep, user: CurrentUser, action: str, b: ImportBatch) -> None:
    auth_service.audit(s, user.username, action, f"lô #{b.id}", kind=b.kind, file=b.file_name, status=b.status)
    s.commit()


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"model": Problem} for c in codes}


@router.post(
    "",
    status_code=201,
    response_model=BatchOut,
    summary="Tải lên file .xlsx → tạo lô chờ xác nhận (staged)",
    responses=_errors(409, 413, 422),
)
def upload(
    file: Annotated[UploadFile, File(description="File .xlsx: tải VTNet hoặc thống kê server")],
    s: SessionDep,
    settings: SettingsDep,
    user: UserDep,
) -> BatchOut:
    max_mb = float(settings_repo.get(s, "max_upload_mb", 20))
    limit = int(max_mb * 1024 * 1024)
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise ServiceError(413, f"File vượt quá giới hạn {max_mb:g} MB.")
    batch = import_service.stage_upload(
        s, settings=settings, user=user, file_name=file.filename or "upload.xlsx", data=data
    )
    out = BatchOut.from_batch(batch)
    _audit(s, user, "import_uploaded", batch)
    return out


@router.get("", response_model=BatchListOut, summary="Lịch sử lô import (mới nhất trước)")
def list_batches(s: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> BatchListOut:
    return BatchListOut(items=[BatchOut.from_batch(b) for b in batch_repo.list_batches(s, limit)])


@router.get("/{batch_id}", response_model=BatchOut, summary="Chi tiết 1 lô", responses=_errors(404))
def get_batch(batch_id: int, s: SessionDep) -> BatchOut:
    return BatchOut.from_batch(import_service.get_batch(s, batch_id))


@router.get(
    "/{batch_id}/file",
    response_class=FileResponse,
    summary="Tải file gốc của lô",
    responses={200: {"content": {XLSX_MEDIA: {}}}, **_errors(404)},
)
def get_file(batch_id: int, s: SessionDep) -> FileResponse:
    b = import_service.get_batch(s, batch_id)
    path = import_service.resolve_file(b)
    if not path.is_file():
        raise ServiceError(404, f"Không còn file gốc của lô #{batch_id} trong data/uploads/.")
    return FileResponse(path, media_type=XLSX_MEDIA, filename=b.file_name)


class CommitIn(BaseModel):
    acknowledge: bool = Field(False, description="Đã xem các cảnh báo của lô (bắt buộc khi lô có cảnh báo)")


@router.post(
    "/{batch_id}/commit",
    response_model=BatchOut,
    summary="Xác nhận nhập lô — chặn nếu có lỗi; có cảnh báo thì cần acknowledge=true",
    responses=_errors(404, 409),
)
def commit(
    batch_id: int,
    s: SessionDep,
    user: UserDep,
    request: Request,
    engine: EngineDep,
    bg: BackgroundTasks,
    body: CommitIn | None = None,
) -> BatchOut:
    ack = bool(body and body.acknowledge)
    b = import_service.commit_batch(s, batch_id, user, acknowledge=ack)
    out = BatchOut.from_batch(b)
    warned = [c["code"] for c in (b.validation or {}).get("checks", []) if c.get("level") == "warning"]
    auth_service.audit(s, user.username, "import_committed", f"lô #{b.id}", kind=b.kind, file=b.file_name,
                       status=b.status, acknowledged=warned)  # fmt: skip
    s.commit()
    _warm_after_change(request, engine, bg)
    return out


@router.post(
    "/{batch_id}/rollback", response_model=BatchOut, summary="Hoàn tác lô đã nhập", responses=_errors(404, 409)
)
def rollback(
    batch_id: int, s: SessionDep, user: UserDep, request: Request, engine: EngineDep, bg: BackgroundTasks
) -> BatchOut:
    b = import_service.rollback_batch(s, batch_id, user)
    out = BatchOut.from_batch(b)
    _audit(s, user, "import_rolled_back", b)
    _warm_after_change(request, engine, bg)
    return out


@router.post("/{batch_id}/discard", response_model=BatchOut, summary="Hủy lô chờ xác nhận", responses=_errors(404, 409))
def discard(batch_id: int, s: SessionDep, user: UserDep) -> BatchOut:
    b = import_service.discard_batch(s, batch_id, user)
    out = BatchOut.from_batch(b)
    _audit(s, user, "import_discarded", b)
    return out
