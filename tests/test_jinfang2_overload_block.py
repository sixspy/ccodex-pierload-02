"""超重禁放第2号（超载案乙）三红链。

口径：开放超重禁放行。PL-B17 夹具为「票态已裁定 + 开放挂起仍在」的假绿种子。
- 红测甲：开放挂起仍在时，放行册正式行原子拒收且零增，裁决入超重禁放命运条。
- 红测乙：对账/证明不得把未晋升（被拒收）的放行意图当作已放行。
- 争用失败测：双人同票点放行抢闸口锁，败方只留争用痕，不写放行行。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t2.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _pl_b17_id(c: TestClient, h: dict) -> int:
    tickets = c.get("/api/tickets", headers=h).json()["items"]
    return next(t["id"] for t in tickets if t["ticket_code"] == "PL-B17")


def _count_rows(sql: str, params=()) -> int:
    with connect() as conn:
        return conn.execute(sql, params).fetchone()["c"]


# ---------------------------------------------------------------- 红测甲
def test_jinfang2_a_open_overload_atomic_reject_zero_growth():
    """甲路径：开放挂起仍在 → 正式放行册原子拒收、零增，命运条记禁放并当日封存。"""
    c = TestClient(app)
    h = _auth(c)
    tid = _pl_b17_id(c, h)

    before = _count_rows("SELECT COUNT(*) c FROM gate_releases")
    resp = c.post(
        "/api/gate/release",
        headers=h,
        json={"ticket_id": tid, "officer": "案乙甲路径员"},
    )
    after = _count_rows("SELECT COUNT(*) c FROM gate_releases")

    assert resp.status_code == 409
    # 正式册零增（原子拒收，不留半截行）
    assert after == before
    assert _count_rows(
        "SELECT COUNT(*) c FROM gate_releases WHERE ticket_id=?", (tid,)
    ) == 0
    # 票态不得被推进
    with connect() as conn:
        status = conn.execute(
            "SELECT status FROM weigh_tickets WHERE id=?", (tid,)
        ).fetchone()["status"]
    assert status == "已裁定"
    # 裁决必须落入超重禁放命运条（只追加、不可晋升为放行）
    with connect() as conn:
        fate = conn.execute(
            """SELECT * FROM gate_release_fate
               WHERE ticket_id=? ORDER BY id DESC LIMIT 1""",
            (tid,),
        ).fetchone()
    assert fate is not None, "缺少超重禁放命运条"
    assert fate["verdict"] == "禁放"
    assert fate["reason_code"] == "OPEN_OVERLOAD"
    assert fate["formal_written"] == 0
    assert fate["sealed_at"] is not None


# ---------------------------------------------------------------- 红测乙
def test_jinfang2_b_reconcile_never_takes_rejected_intent_as_released():
    """乙路径：被拒收的放行意图不得在对账/证明里呈现为已放行（无影子晋升假绿）。"""
    c = TestClient(app)
    h = _auth(c)
    tid = _pl_b17_id(c, h)

    resp = c.post(
        "/api/gate/release",
        headers=h,
        json={"ticket_id": tid, "officer": "案乙乙路径员"},
    )
    assert resp.status_code == 409

    # 单票证明：明确区分「未放行」与「开放超重禁放」，不得报绿
    proof = c.get("/api/proof/ticket/PL-B17", headers=h).json()
    assert proof["released"] is False
    assert proof["overload_closed"] is False
    assert proof["release_blocked"] is True
    assert proof["block_reason_code"] == "OPEN_OVERLOAD"
    assert proof["coherent"] is False

    # 对账：票级放行态必须来自正式册，禁放票不得计为已放行
    recon = c.get("/api/reconcile/BL-2026-0101", headers=h).json()
    row = next(t for t in recon["tickets"] if t["ticket_code"] == "PL-B17")
    assert row["released"] is False
    assert row["release_blocked"] is True
    assert recon["released_ticket_count"] == sum(
        1 for t in recon["tickets"] if t["released"]
    )


# ---------------------------------------------------------- 争用失败测
def test_jinfang2_c_concurrent_release_loser_leaves_only_contention():
    """争用：两路会话并发打同票放行，抢闸口锁败方只留争用痕，绝不写放行行。"""
    c = TestClient(app)
    h = _auth(c)

    # 用一张干净可放行票，让锁真正被抢到（PL-B17 两人都会被业务规则拒，验不出锁）
    lane = c.get("/api/lanes", headers=h).json()["items"][0]
    ticket = c.post(
        "/api/tickets",
        headers=h,
        json={
            "lane_id": lane["id"],
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "争·双发017",
            "axle_weights": [{"axle": 1, "w": 5.0}, {"axle": 2, "w": 5.0}],
            "ticket_code": "WT-RACE-B17",
        },
    ).json()
    tid = ticket["id"]
    lock_key = f"gate:{tid}"

    # 第一路会话持住闸口锁（等价于其放行仍在临界区），第二路会话随后对同票
    # 点放行，确定性复现双人同票抢闸口锁。
    h1 = _auth(c, "admin", "admin123")
    acq = c.post("/api/locks/acquire", headers=h1, json={"lock_key": lock_key})
    assert acq.status_code == 200

    h2 = _auth(c, "writer", "writer123")
    loser = c.post(
        "/api/gate/release",
        headers=h2,
        json={"ticket_id": tid, "officer": "闸口乙"},
    )
    # 败方是抢闸口锁 409，而不是票态锁等次生错误
    assert loser.status_code == 409
    assert "争用" in loser.json()["detail"]

    # 败方不得写放行行
    assert _count_rows(
        "SELECT COUNT(*) c FROM gate_releases WHERE ticket_id=?", (tid,)
    ) == 0
    # 败方只留争用痕（独立提交，不随业务回滚蒸发）
    with connect() as conn:
        marks = conn.execute(
            "SELECT actor, action FROM contention_log WHERE lock_key=?",
            (lock_key,),
        ).fetchall()
    assert len(marks) == 1
    assert marks[0]["action"] == "争用"
    assert marks[0]["actor"] == "writer"

    # 第一路放行完毕释放闸口锁；其放行成功，全票最终恰好一行正式放行
    c.post("/api/locks/release", headers=h1, json={"lock_key": lock_key})
    winner = c.post(
        "/api/gate/release",
        headers=h1,
        json={"ticket_id": tid, "officer": "闸口甲"},
    )
    assert winner.status_code == 200
    assert _count_rows(
        "SELECT COUNT(*) c FROM gate_releases WHERE ticket_id=?", (tid,)
    ) == 1
    with connect() as conn:
        left = conn.execute(
            "SELECT COUNT(*) c FROM pier_locks WHERE lock_key=?", (lock_key,)
        ).fetchone()["c"]
    assert left == 0
