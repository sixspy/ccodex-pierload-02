"""过磅与闸口校验。"""
from __future__ import annotations

from fastapi import HTTPException

from db import BLOCK_REASON_OPEN_OVERLOAD, now_iso


def open_overload_hold(conn, ticket_id: int):
    """返回该票仍开放的超重挂起；无则 None。"""
    return conn.execute(
        """SELECT h.* FROM overload_holds h
           WHERE h.ticket_id=? AND h.status='开放'
           ORDER BY h.id DESC LIMIT 1""",
        (ticket_id,),
    ).fetchone()


def validate_lane_open(lane: dict) -> None:
    if lane["status"] not in ("开放", "维护"):
        raise HTTPException(409, "车道已关闭")
    if lane["status"] == "维护":
        raise HTTPException(409, "车道维护中禁止过磅")


def validate_axle_count(axles: list, axle_limit: int) -> None:
    if len(axles) < 2:
        raise HTTPException(422, "至少两根轴重")
    if len(axles) > axle_limit:
        raise HTTPException(422, f"轴数超限（限 {axle_limit} 轴）")


def validate_axle_weights(axles: list) -> tuple[float, float, float]:
    weights = []
    for a in axles:
        w = float(a.get("w", a.w if hasattr(a, "w") else 0))
        if w <= 0:
            raise HTTPException(422, "轴重须为正")
        weights.append(w)
    gross = round(sum(weights), 3)
    peak_axle = max(weights)
    spread = peak_axle - min(weights)
    return gross, peak_axle, spread


def validate_gross_cap(gross: float, max_gross: float) -> None:
    if gross > max_gross * 1.15:
        raise HTTPException(422, "毛重远超地磅额定量程")
    if gross <= 0:
        raise HTTPException(422, "毛重无效")


def validate_bl_match(declared: float, gross: float, tolerance: float = 0.08) -> bool:
    if declared <= 0:
        return False
    return abs(gross - declared) / declared <= tolerance


def adjudicate_overload(gross: float, threshold: float) -> tuple[bool, float]:
    overweight = round(gross - threshold, 3)
    return overweight > 0, max(overweight, 0.0)


def validate_ticket_mutable(ticket: dict) -> None:
    if ticket["status"] in ("已封闸", "已放行", "作废"):
        raise HTTPException(409, "票态已锁定")


def validate_ticket_sealable(ticket: dict) -> None:
    if ticket["status"] in ("已封闸", "作废"):
        raise HTTPException(409, "票态已锁定")


def record_release_fate(
    conn,
    ticket_id: int,
    ticket_code: str,
    officer: str,
    verdict: str,
    reason_code: str,
    detail: str,
    formal_written: bool = False,
) -> int:
    """追加一条放行命运条。只允许 INSERT：禁放条当日封存，不提供改/删/晋升。"""
    cur = conn.execute(
        """INSERT INTO gate_release_fate(ticket_id,ticket_code,officer,verdict,
           reason_code,detail,formal_written,sealed_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            ticket_id,
            ticket_code,
            officer,
            verdict,
            reason_code,
            detail,
            1 if formal_written else 0,
            now_iso(),
        ),
    )
    return cur.lastrowid


def format_manifest(ticket: dict, gross: float, generation: int) -> str:
    return (
        f"票号={ticket['ticket_code']};"
        f"提单={ticket['bl_ref']};"
        f"车牌={ticket['vehicle_plate']};"
        f"毛重={gross}t;"
        f"闸代={generation}"
    )