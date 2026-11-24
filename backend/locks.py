"""码头锁与争用登记（独立短连接，锁事务不与业务事务互锁）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])


class LockIn(BaseModel):
    lock_key: str
    action: str = "acquire"


def try_acquire(conn, lock_key: str, holder: str) -> bool:
    """兼容旧签名：在给定连接上试探（仅锁管理端点使用）。"""
    now = now_iso()
    row = conn.execute(
        "SELECT holder FROM pier_locks WHERE lock_key=?", (lock_key,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO pier_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
            (lock_key, holder, now),
        )
        return True
    if row["holder"] == holder:
        return True
    conn.execute(
        """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
           VALUES (?,?,?,?,?)""",
        (lock_key, holder, "争用", f"持有者={row['holder']}", now),
    )
    return False


def acquire_pier_lock(lock_key: str, holder: str) -> bool:
    """独立短连接抢码头锁并立即提交，避免长事务占住 SQLite 写位。"""
    with connect() as conn:
        now = now_iso()
        row = conn.execute(
            "SELECT holder FROM pier_locks WHERE lock_key=?", (lock_key,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO pier_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
                (lock_key, holder, now),
            )
            conn.commit()
            return True
        if row["holder"] == holder:
            return True
        # 争用痕独立事务提交：败方随后抛 409，痕迹不随业务回滚蒸发
        conn.execute(
            """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
               VALUES (?,?,?,?,?)""",
            (lock_key, holder, "争用", f"持有者={row['holder']}", now),
        )
        write_audit(
            conn,
            holder,
            "lock_contention",
            lock_key,
            {"holder": row["holder"]},
        )
        conn.commit()
        return False


def ticket_gate_lock_key(ticket_id: int) -> str:
    """同票写操作统一闸口锁键：放行/超重/封闸共用，消除跨域竞态窗口。"""
    return f"gate:{ticket_id}"


def release(conn, lock_key: str, holder: str) -> None:
    conn.execute(
        "DELETE FROM pier_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


def release_pier_lock(lock_key: str, holder: str) -> None:
    with connect() as conn:
        release(conn, lock_key, holder)
        conn.commit()


def require_lock(conn, lock_key: str, holder: str) -> None:
    if not try_acquire(conn, lock_key, holder):
        raise HTTPException(409, "争用：后到只记争用，不写业务")


def require_pier_lock(lock_key: str, holder: str) -> None:
    """抢码头锁：失败即 409，争用痕已独立落库。"""
    if not acquire_pier_lock(lock_key, holder):
        raise HTTPException(409, "争用：后到只记争用，不写业务")


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pier_locks ORDER BY acquired_at DESC"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/contention")
def list_contention(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contention_log ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/locks/acquire")
def acquire_lock(body: LockIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        ok = try_acquire(conn, body.lock_key, user)
        write_audit(conn, user, "lock_acquire", body.lock_key, {"ok": ok})
        conn.commit()
        if not ok:
            raise HTTPException(409, "争用：未能获得锁")
        return {"ok": True, "lock_key": body.lock_key, "holder": user}


@router.post("/api/locks/release")
def release_lock(body: LockIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, body.lock_key, user)
        write_audit(conn, user, "lock_release", body.lock_key, {})
        conn.commit()
        return {"ok": True}