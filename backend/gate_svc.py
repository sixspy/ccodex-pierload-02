"""闸口放行：开放超重未清禁放行（口径唯一，不与影子草稿等写法混用）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import (
    BLOCK_REASON_OPEN_OVERLOAD,
    connect,
    now_iso,
    write_audit,
)
from locks import require_pier_lock, release_pier_lock, ticket_gate_lock_key
from models import GateReleaseIn
from validators import (
    open_overload_hold,
    record_release_fate,
    validate_ticket_mutable,
)

router = APIRouter(tags=["gate"])


@router.get("/api/gate/releases")
def list_releases(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT g.*, t.ticket_code, t.vehicle_plate, l.lane_code
               FROM gate_releases g
               JOIN weigh_tickets t ON t.id=g.ticket_id
               JOIN weigh_lanes l ON l.id=g.lane_id
               ORDER BY g.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/gate/fate")
def list_release_fate(authorization: AuthHeader = None):
    """超重禁放命运条只读列表（只追加台账，无写入/晋升入口）。"""
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM gate_release_fate ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/gate/release")
def release_gate(body: GateReleaseIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = ticket_gate_lock_key(body.ticket_id)
    # 抢闸口锁（独立短连接）：败方在此直接 409，争用痕已落库，不写任何业务行
    require_pier_lock(lock_key, user)
    try:
        with connect() as conn:
            ticket = conn.execute(
                """SELECT t.*, l.id lane_id FROM weigh_tickets t
                   JOIN weigh_lanes l ON l.id=t.lane_id WHERE t.id=?""",
                (body.ticket_id,),
            ).fetchone()
            if not ticket:
                raise HTTPException(404, "过磅票不存在")
            ticket = dict(ticket)
            validate_ticket_mutable(ticket)
            if ticket["status"] not in ("已裁定", "旁路挂起"):
                raise HTTPException(409, "票态不允许放行")
            if ticket["status"] == "旁路挂起":
                raise HTTPException(409, "旁路挂起须先闭环")

            # 甲路径原子拒收：开放挂起仍在 → 禁放命运条独立事务当日封存，
            # 正式放行册零增；随后 409 回滚主事务，命运条因已提交而留存。
            hold = open_overload_hold(conn, body.ticket_id)
            if hold:
                with connect() as fate_conn:
                    record_release_fate(
                        fate_conn,
                        ticket_id=ticket["id"],
                        ticket_code=ticket["ticket_code"],
                        officer=body.officer,
                        verdict="禁放",
                        reason_code=BLOCK_REASON_OPEN_OVERLOAD,
                        detail=(
                            f"开放挂起 {hold['hold_key']} 未闭环，放行意图原子拒收，"
                            "正式册零增"
                        ),
                        formal_written=False,
                    )
                    write_audit(
                        fate_conn,
                        user,
                        "gate_release_blocked",
                        ticket["ticket_code"],
                        {
                            "ticket_id": ticket["id"],
                            "reason_code": BLOCK_REASON_OPEN_OVERLOAD,
                            "hold_key": hold["hold_key"],
                        },
                    )
                    fate_conn.commit()
                raise HTTPException(409, "存在开放超重挂起，不得放行")

            exists = conn.execute(
                "SELECT id FROM gate_releases WHERE ticket_id=? AND status='已放行'",
                (body.ticket_id,),
            ).fetchone()
            if exists:
                raise HTTPException(409, "已放行")
            now = now_iso()
            ref = f"GR-{ticket['ticket_code']}-{now[:10]}"
            cur = conn.execute(
                """INSERT INTO gate_releases(ticket_id,lane_id,release_ref,status,officer,released_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    body.ticket_id,
                    ticket["lane_id"],
                    ref,
                    "已放行",
                    body.officer,
                    now,
                ),
            )
            conn.execute(
                "UPDATE weigh_tickets SET status='已放行' WHERE id=?",
                (body.ticket_id,),
            )
            # 放行裁决同样入命运条：与正式行同一事务，同成同败
            record_release_fate(
                conn,
                ticket_id=body.ticket_id,
                ticket_code=ticket["ticket_code"],
                officer=body.officer,
                verdict="放行",
                reason_code="CLEARED",
                detail=f"正式放行 {ref}，无开放超重挂起",
                formal_written=True,
            )
            write_audit(
                conn,
                user,
                "gate_release",
                ref,
                {"release_id": cur.lastrowid, "ticket_id": body.ticket_id},
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "release_ref": ref,
                "status": "已放行",
            }
    finally:
        release_pier_lock(lock_key, user)
