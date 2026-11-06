"""Đối soát + liên kết IP (G2-M3, PLAN §8.6, CONTEXT §6): VTNet có – thống kê thiếu · thống kê có – không có số liệu
(đã thu hồi / chưa rõ) · lệch số card · liên kết IP (sửa cặp, xác nhận, xóa) · gợi ý liên kết theo nhóm (số card, model GPU).

Dựng lại từ `analytics_service.catalog` (cùng nguồn với Danh mục server) — không có công thức mới. Gợi ý chỉ là gợi ý:
admin duyệt từng cặp, code không tự áp. Đổi liên kết → `data_version` đổi → phân tích tính lại.
"""

from __future__ import annotations

import ipaddress
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

import gpu_core as g
from app.db.models import IpLink
from app.errors import ServiceError
from app.repo import inventory_repo
from app.repo.convert import py
from app.scope import Scope
from app.services.analytics_service import Bundle, Filters, catalog
from app.services.auth_service import audit, utcnow

VTNET_FIELDS = ["ip", "gpu_type", "gpu_count", "gpu_model", "zone", "pattern", "gpu_avg", "mem_avg", "days",
                "vtnet_low_load"]  # fmt: skip
INV_FIELDS = ["inventory_ip", "ip", "owner", "service", "model", "cluster", "inventory_gpu_spec", "gpu_count",
              "gpu_model", "data_status", "excel_row"]  # fmt: skip
MISMATCH_FIELDS = ["inventory_ip", "ip", "owner", "service", "inventory_gpu_spec", "gpu_type", "gpu_count", "gpu_model",
                   "zone", "ip_linked"]  # fmt: skip


def _ip_key(ip: Any) -> int:
    try:
        return int(ipaddress.IPv4Address(str(ip)))
    except ValueError:
        return 1 << 33


def _pick(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {f: row.get(f) for f in fields}


def gaps(b: Bundle, scope: Scope) -> dict[str, Any]:
    cat = catalog(b, Filters(), scope)
    rows: list[dict[str, Any]] = cat["items"]
    vt_only = [_pick(r, VTNET_FIELDS) for r in rows if r["row_type"] == "vtnet_only"]
    inv_rows = [r for r in rows if r["row_type"] == "inventory"]
    reclaimed = [_pick(r, INV_FIELDS) for r in inv_rows if r["data_status"] == "reclaimed"]
    unknown = [_pick(r, INV_FIELDS) for r in inv_rows if r["data_status"] == "no_data"]
    mismatch = [_pick(r, MISMATCH_FIELDS) for r in inv_rows if r["gpu_count_mismatch"]]
    links = link_rows(b, scope)
    return {
        "params": cat["params"],
        "counts": {
            "vtnet_only": len(vt_only),
            "no_data": len(reclaimed) + len(unknown),
            "reclaimed": len(reclaimed),
            "unknown": len(unknown),
            "gpu_count_mismatch": len(mismatch),
            "links": len(links),
            "links_unconfirmed": sum(1 for x in links if not x["pair_confirmed"]),
            "manual": cat["counts"]["manual"],
        },
        "vtnet_only": vt_only,
        "reclaimed": reclaimed,
        "unknown": unknown,
        "gpu_count_mismatch": mismatch,
        "suggestions": suggestions(vt_only, unknown),
    }


def suggestions(vt_only: list[dict[str, Any]], unknown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nhóm VTNet-only và thống kê-không-số-liệu theo (số card, model GPU). Hai bên cùng số máy → đề xuất ghép theo IP tăng
    dần (cách người dùng đã chốt cho 9 máy RTX6000, CONTEXT §6); khác số máy → chỉ liệt kê, admin tự chọn."""

    def key(r: dict[str, Any]) -> tuple[int, str] | None:
        c, m = r.get("gpu_count"), r.get("gpu_model")
        return (int(c), str(m)) if c is not None and m else None

    groups: dict[tuple[int, str], tuple[list[str], list[str]]] = {}
    for r in vt_only:
        k = key(r)
        if k:
            groups.setdefault(k, ([], []))[0].append(str(r["ip"]))
    for r in unknown:
        k = key(r)
        if k and k in groups:
            groups[k][1].append(str(r["inventory_ip"]))
    out = []
    for (count, model), (vt, inv) in sorted(groups.items()):
        if not inv:
            continue
        vt, inv = sorted(vt, key=_ip_key), sorted(inv, key=_ip_key)
        pairs = (
            [{"inventory_ip": i, "vtnet_ip": v} for i, v in zip(inv, vt, strict=True)] if len(vt) == len(inv) else []
        )
        out.append({"gpu_count": count, "gpu_model": model, "vtnet_ips": vt, "inventory_ips": inv, "pairs": pairs})
    return out


# ------------------------------------------------------------------ liên kết IP


def link_rows(b: Bundle, scope: Scope) -> list[dict[str, Any]]:
    inv = b.inventory.set_index("inventory_ip") if not b.inventory.empty else pd.DataFrame()
    measured = set(b.servers["ip"]) if not b.servers.empty else set()
    zone = dict(zip(b.servers["ip"], b.servers["zone"], strict=True)) if not b.servers.empty else {}
    out = []
    for r in b.links.to_dict("records"):
        iip = r["inventory_ip"]
        present = iip in inv.index
        owner = py(inv.at[iip, "owner"]) if present else None
        if scope.kind == "owner" and owner != scope.owner_key:
            continue
        out.append(
            {
                "inventory_ip": iip,
                "vtnet_ip": r["vtnet_ip"],
                "pair_confirmed": bool(r["pair_confirmed"]),
                "reason": py(r.get("reason")),
                "owner": owner,
                "service": py(inv.at[iip, "service"]) if present else None,
                "inventory_gpu_spec": py(inv.at[iip, "inventory_gpu_spec"]) if present else None,
                "in_inventory": present,
                "vtnet_has_data": r["vtnet_ip"] in measured,
                "zone": zone.get(r["vtnet_ip"]),
            }
        )
    return sorted(out, key=lambda x: _ip_key(x["inventory_ip"]))


def link_details(s: Session) -> dict[str, dict[str, Any]]:
    """Người tạo / xác nhận + thời điểm của từng liên kết (để hiện trên Đối soát)."""
    return {
        x.inventory_ip: {
            "created_by": x.created_by,
            "created_at": x.created_at,
            "confirmed_by": x.confirmed_by,
            "confirmed_at": x.confirmed_at,
        }
        for x in s.scalars(select(IpLink))
    }


def _norm_ip(value: str, label: str) -> str:
    ip = g.norm_ip(value)
    if not g.is_ipv4(ip):
        raise ServiceError(422, f"{label} không phải IPv4 hợp lệ: {value!r}.")
    return ip


def _check(s: Session, links: list[tuple[str, str]]) -> None:
    """Toàn bộ liên kết sau khi đổi phải hợp lệ với file thống kê hiện hành (không 2 dòng cùng trỏ 1 máy)."""
    inv = [i for i, _ in links]
    vt = [v for _, v in links]
    for a, b in links:
        if a == b:
            raise ServiceError(422, f"IP thống kê và IP VTNet trùng nhau ({a}).")
    if len(set(inv)) != len(inv):
        raise ServiceError(409, "Mỗi IP thống kê chỉ có 1 liên kết.")
    if len(set(vt)) != len(vt):
        dup = sorted({v for v in vt if vt.count(v) > 1})
        raise ServiceError(409, f"IP VTNet {', '.join(dup)} đã được liên kết với IP thống kê khác.")
    df = pd.DataFrame(links, columns=["inventory_ip", "vtnet_ip"])
    try:
        g.apply_ip_links(inventory_repo.current_frame(s), df)
    except ValueError as exc:
        raise ServiceError(
            409, f"Liên kết làm 2 dòng thống kê cùng trỏ 1 máy VTNet: {exc} — IP VTNet đó đã có dòng thống kê riêng."
        ) from exc


def _current(s: Session) -> dict[str, IpLink]:
    return {x.inventory_ip: x for x in s.scalars(select(IpLink))}


def create_link(s: Session, actor: str, inventory_ip: str, vtnet_ip: str, reason: str | None) -> IpLink:
    iip, vip = _norm_ip(inventory_ip, "IP thống kê"), _norm_ip(vtnet_ip, "IP VTNet")
    cur = _current(s)
    if iip in cur:
        raise ServiceError(409, f"IP thống kê {iip} đã có liên kết (→ {cur[iip].vtnet_ip}) — sửa liên kết đó.")
    _check(s, [(x.inventory_ip, x.vtnet_ip) for x in cur.values()] + [(iip, vip)])
    link = IpLink(
        inventory_ip=iip, vtnet_ip=vip, pair_confirmed=False, reason=(reason or "").strip() or None,
        created_by=actor, created_at=utcnow(),
    )  # fmt: skip
    s.add(link)
    audit(s, actor, "link_created", iip, vtnet_ip=vip, reason=link.reason)
    s.commit()
    return link


def update_link(s: Session, actor: str, inventory_ip: str, changes: dict[str, Any]) -> IpLink:
    cur = _current(s)
    iip = g.norm_ip(inventory_ip)
    link = cur.get(iip)
    if link is None:
        raise ServiceError(404, f"Không có liên kết cho IP thống kê {inventory_ip}.")
    before = {
        "inventory_ip": link.inventory_ip, "vtnet_ip": link.vtnet_ip, "pair_confirmed": link.pair_confirmed,
        "reason": link.reason,
    }  # fmt: skip
    # Đổi IP thống kê của cặp (PLAN §14.12, người dùng chốt 06/11/2026): IP mới phải có trong file thống kê hiện hành và chưa
    # có liên kết; khóa chính đổi → tạo dòng mới, bỏ dòng cũ; cặp mới phải xác nhận lại.
    new_iip = changes.get("inventory_ip")
    if new_iip is not None and g.norm_ip(new_iip) != iip:
        new_iip = _norm_ip(new_iip, "IP thống kê")
        if new_iip in cur:
            raise ServiceError(
                409, f"IP thống kê {new_iip} đã có liên kết (→ {cur[new_iip].vtnet_ip}) — sửa liên kết đó."
            )
        if inventory_repo.current_row(s, new_iip) is None:
            raise ServiceError(422, f"IP thống kê {new_iip} không có trong file thống kê hiện hành.")
        vip_after = _norm_ip(changes["vtnet_ip"], "IP VTNet") if changes.get("vtnet_ip") else link.vtnet_ip
        pairs = [(x.inventory_ip, x.vtnet_ip) for x in cur.values() if x.inventory_ip != iip] + [(new_iip, vip_after)]
        _check(s, pairs)
        moved = IpLink(
            inventory_ip=new_iip, vtnet_ip=vip_after, pair_confirmed=False, reason=link.reason,
            created_by=link.created_by, created_at=link.created_at,
        )  # fmt: skip
        s.delete(link)
        s.flush()  # giải phóng ràng buộc unique vtnet_ip trước khi thêm dòng mới
        s.add(moved)
        link, iip = moved, new_iip
        changes = {k: v for k, v in changes.items() if k not in ("inventory_ip", "vtnet_ip")}
    if "vtnet_ip" in changes and changes["vtnet_ip"] is not None:
        vip = _norm_ip(changes["vtnet_ip"], "IP VTNet")
        if vip != link.vtnet_ip:
            _check(s, [(x.inventory_ip, vip if x.inventory_ip == iip else x.vtnet_ip) for x in cur.values()])
            link.vtnet_ip = vip
            link.pair_confirmed, link.confirmed_by, link.confirmed_at = False, None, None  # đổi cặp → phải xác nhận lại
    if "reason" in changes:
        link.reason = (changes["reason"] or "").strip() or None
    if changes.get("pair_confirmed") is not None:
        confirmed = bool(changes["pair_confirmed"])
        if confirmed and not link.pair_confirmed:
            link.pair_confirmed, link.confirmed_by, link.confirmed_at = True, actor, utcnow()
        elif not confirmed:
            link.pair_confirmed, link.confirmed_by, link.confirmed_at = False, None, None
    after = {
        "inventory_ip": link.inventory_ip, "vtnet_ip": link.vtnet_ip, "pair_confirmed": link.pair_confirmed,
        "reason": link.reason,
    }  # fmt: skip
    action = "link_confirmed" if after["pair_confirmed"] and not before["pair_confirmed"] else "link_updated"
    audit(s, actor, action, iip, before=before, after=after)
    s.commit()
    return link


def delete_link(s: Session, actor: str, inventory_ip: str) -> None:
    iip = g.norm_ip(inventory_ip)
    link = _current(s).get(iip)
    if link is None:
        raise ServiceError(404, f"Không có liên kết cho IP thống kê {inventory_ip}.")
    audit(s, actor, "link_deleted", iip, vtnet_ip=link.vtnet_ip, pair_confirmed=link.pair_confirmed)
    s.delete(link)
    s.commit()
