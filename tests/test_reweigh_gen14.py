"""二次升代第14号三红：同车双正式并存（PL-N14a / PL-N14b）。

种子夹具：沪N·集1414 在 BL-2026-0114 上双正式并存（均「已裁定」）。
测甲：二次过磅升代互斥写路径——同事务作废旧票、升新代正式、零净增、回滚与偏航拒写。
测乙：影子新代未晋升却被对账双计——对账不得双计、双正式显式冲突、封闸拒写。
争用：双会话同车号抢二次过磅——车号锁，后到只留争用痕。
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db

PLATE = "沪N·集1414"
BL = "BL-2026-0114"
LOCK_KEY = f"vehicle:{PLATE}"


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _lane_id(c: TestClient, h: dict, code="LN-N-01-IN") -> int:
    lanes = c.get("/api/lanes", headers=h).json()["items"]
    return next(x for x in lanes if x["lane_code"] == code)["id"]


def _tickets(c: TestClient, h: dict) -> list:
    return c.get("/api/tickets", headers=h).json()["items"]


def _formal(c: TestClient, h: dict, plate: str, bl: str) -> list:
    return [
        t
        for t in _tickets(c, h)
        if t["vehicle_plate"] == plate and t["bl_ref"] == bl and t["status"] != "作废"
    ]


def test_14a_reweigh_atomic_void_and_promote():
    """测甲：再次过磅须同事务作废旧票并升新代正式，零净增，否则整笔回滚。"""
    c = TestClient(app)
    h = _auth(c)
    lane_id = _lane_id(c, h)
    first = c.post(
        "/api/tickets",
        headers=h,
        json={
            "lane_id": lane_id,
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "沪T·升代14",
            "axle_weights": [{"axle": 1, "w": 20.0}, {"axle": 2, "w": 20.0}],
            "ticket_code": "PL-T14-OLD",
        },
    )
    assert first.status_code == 200 and first.json()["status"] == "已裁定"
    # 二次过磅：升代互斥写路径
    rw = c.post(
        "/api/tickets/reweigh",
        headers=h,
        json={
            "lane_id": lane_id,
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "沪T·升代14",
            "axle_weights": [{"axle": 1, "w": 20.5}, {"axle": 2, "w": 20.5}],
            "ticket_code": "PL-T14-NEW",
            "reason": "复磅纠偏",
        },
    )
    assert rw.status_code == 200, rw.text
    body = rw.json()
    assert body["status"] == "已裁定"
    assert body["voided"] == ["PL-T14-OLD"]
    # 旧票已作废、新票正式、正式零净增
    formal = _formal(c, h, "沪T·升代14", "BL-2026-0101")
    assert [t["ticket_code"] for t in formal] == ["PL-T14-NEW"]
    old = next(t for t in _tickets(c, h) if t["ticket_code"] == "PL-T14-OLD")
    assert old["status"] == "作废"
    # 血缘升代边：旧票 → 新代，两端票态同源可见
    edges = c.get("/api/lineage", headers=h).json()["items"]
    edge = next(e for e in edges if e["edge_type"] == "二次过磅升代")
    assert edge["from_code"] == "PL-T14-OLD" and edge["to_code"] == "PL-T14-NEW"
    assert edge["from_status"] == "作废" and edge["to_status"] == "已裁定"
    # 整笔回滚：票号冲突时旧票不得被作废、正式数不得动
    dup = c.post(
        "/api/tickets/reweigh",
        headers=h,
        json={
            "lane_id": lane_id,
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "沪T·升代14",
            "axle_weights": [{"axle": 1, "w": 21.0}, {"axle": 2, "w": 21.0}],
            "ticket_code": "PL-T14-NEW",
        },
    )
    assert dup.status_code == 409
    formal = _formal(c, h, "沪T·升代14", "BL-2026-0101")
    assert [t["ticket_code"] for t in formal] == ["PL-T14-NEW"]
    # 偏航拒写：乙路径等影子口径一律记「二次升代偏航」并拒写
    dev = c.post(
        "/api/tickets/reweigh",
        headers=h,
        json={
            "lane_id": lane_id,
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "沪T·升代14",
            "axle_weights": [{"axle": 1, "w": 21.0}, {"axle": 2, "w": 21.0}],
            "ticket_code": "PL-T14-SHD",
            "mode": "乙",
        },
    )
    assert dev.status_code == 409
    audits = c.get("/api/audit", headers=h).json()["items"]
    assert any(a["action"] == "二次升代偏航" for a in audits)
    assert not any(t["ticket_code"] == "PL-T14-SHD" for t in _tickets(c, h))


def test_14b_shadow_unpromoted_not_double_counted():
    """测乙：影子新代未晋升却被对账双计——对账不得双计，封闸拒双正式。"""
    c = TestClient(app)
    h = _auth(c)
    # 种子夹具：同车双正式并存
    formal = _formal(c, h, PLATE, BL)
    assert {t["ticket_code"] for t in formal} == {"PL-N14a", "PL-N14b"}
    # 对账：只计最新正式票（PL-N14b 42.0t），不得双计（83.8t）；双正式显式上抛
    recon = c.get(f"/api/reconcile/{BL}", headers=h).json()
    assert recon["ticket_sum_t"] == 42.0
    assert recon["double_formal"] is True
    assert "PL-N14a" in {t["ticket_code"] for t in recon["excluded_tickets"]}
    assert recon["balanced"] is False
    assert recon["proof_ready"] is False
    # 双正式未解，封闸拒写
    n14b = next(t for t in _tickets(c, h) if t["ticket_code"] == "PL-N14b")
    seal = c.post("/api/seals", headers=h, json={"ticket_id": n14b["id"]})
    assert seal.status_code == 409


def test_14c_concurrent_reweigh_vehicle_lock():
    """争用：双会话同车号抢二次过磅，车号锁后到只留争用痕。"""
    c = TestClient(app)
    h1 = _auth(c)  # 会话一 admin
    h2 = _auth(c, "writer", "writer123")  # 会话二 writer
    lane_id = _lane_id(c, h1)
    # 会话一先抢车号锁
    assert (
        c.post("/api/locks/acquire", headers=h1, json={"lock_key": LOCK_KEY}).status_code
        == 200
    )
    # 会话二同车号二次过磅：拒写，只留争用痕
    blocked = c.post(
        "/api/tickets/reweigh",
        headers=h2,
        json={
            "lane_id": lane_id,
            "bl_ref": BL,
            "vehicle_plate": PLATE,
            "axle_weights": [{"axle": 1, "w": 21.0}, {"axle": 2, "w": 21.0}],
            "ticket_code": "PL-N14x",
        },
    )
    assert blocked.status_code == 409
    cont = c.get("/api/contention", headers=h1).json()["items"]
    assert any(x["lock_key"] == LOCK_KEY and x["actor"] == "writer" for x in cont)
    assert not any(t["ticket_code"] == "PL-N14x" for t in _tickets(c, h2))
    # 会话一放锁后完成升代：双正式一并作废，新代唯一正式
    assert (
        c.post("/api/locks/release", headers=h1, json={"lock_key": LOCK_KEY}).status_code
        == 200
    )
    rw = c.post(
        "/api/tickets/reweigh",
        headers=h1,
        json={
            "lane_id": lane_id,
            "bl_ref": BL,
            "vehicle_plate": PLATE,
            "axle_weights": [{"axle": 1, "w": 21.25}, {"axle": 2, "w": 21.25}],
            "ticket_code": "PL-N14c",
            "reason": "复磅定案",
        },
    )
    assert rw.status_code == 200, rw.text
    assert sorted(rw.json()["voided"]) == ["PL-N14a", "PL-N14b"]
    formal = _formal(c, h1, PLATE, BL)
    assert [t["ticket_code"] for t in formal] == ["PL-N14c"]
    recon = c.get(f"/api/reconcile/{BL}", headers=h1).json()
    assert recon["ticket_sum_t"] == 42.5
    assert recon["double_formal"] is False
    assert recon["balanced"] is True
