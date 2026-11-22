"""映射切版败例先行（甲路：冻凭证表 / 只读切版落点）。

验收口径：
- 切版必须有落点行；无落点沿旧映射必须失败；只有徽标没有落点必须失败。
- 列指纹不合必须拒采集；徽标与现行映射号拧花必须拒采集。
- 切版单事务串行：两侧同抢只许一成。
- 切版后抓取按新映射写列、按当刻指纹留痕，好件不得被打成坏件。
- 闲置脚手架（map_cutover* 元数据玩具）不得残留。
"""
from __future__ import annotations

import importlib.util
import sqlite3

import pytest

from app.services import captures, mappings, quarantine, review, rework, reconcile
from app.services.errors import ServiceError


# ---------- 脚手架清零 ----------

def test_no_idle_scaffolding_left():
    for name in (
        "app.services.map_cutover",
        "app.services.map_cutover_cutover",
        "app.services.map_cutover_dualwrite",
        "app.services.map_cutover_audit",
    ):
        assert importlib.util.find_spec(name) is None, f"闲置脚手架残留：{name}"


# ---------- 种子即甲路：现行映射 + 只读落点 ----------

def test_seed_has_active_landing_for_v1(db_path):
    gate = mappings.get_gate(db_path)
    assert gate["aligned"] is True
    assert gate["mapping_no"] == "MAP-v1"
    assert gate["mapping_key"] == "catalog.v1"
    assert gate["landing_id"] > 0
    assert gate["column_fingerprint"]
    assert gate["badge"] == "切版已亮"
    landings = mappings.list_landings(db_path)
    assert sum(1 for r in landings if r["is_active"]) == 1


def test_v1_aligned_payload_passes_gate(db_path):
    batch = captures.create_batch("站内目录甲", "指纹批", db_path)
    out = captures.add_item(
        batch["id"], "sku-g1", '{"title":"茶杯","code":"C-1"}', "合格", db_path
    )
    assert out["quality"] == "合格"
    assert out["mapping_no"] == "MAP-v1"
    assert out["column_fingerprint"] == mappings.get_gate(db_path)["column_fingerprint"]


# ---------- 无切版落点 / 只有徽标无落点 ----------

def test_capture_without_landing_must_fail(db_path):
    with sqlite3.connect(db_path) as raw:
        raw.execute("DELETE FROM map_cutover_landings")
        raw.commit()
    batch = captures.create_batch("站内目录甲", "无落点批", db_path)
    with pytest.raises(ServiceError) as ei:
        captures.add_item(
            batch["id"], "sku-x1", '{"title":"茶杯","code":"C-1"}', "合格", db_path
        )
    # 白话报错，禁止静默沿旧映射
    assert "落点" in ei.value.message or "旧映射" in ei.value.message


def test_badge_without_landing_row_must_fail(db_path):
    # 模拟“徽标已亮、落点行缺失”的拧花状态
    with sqlite3.connect(db_path) as raw:
        raw.execute("DELETE FROM map_cutover_landings")
        raw.execute(
            "INSERT INTO meta(key, value) VALUES('map_cutover_badge', '切版已亮') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        raw.commit()
    gate = mappings.get_gate(db_path)
    assert gate["aligned"] is False
    batch = captures.create_batch("站内目录甲", "空徽标批", db_path)
    with pytest.raises(ServiceError) as ei:
        captures.add_item(
            batch["id"], "sku-x2", '{"title":"茶杯","code":"C-1"}', "合格", db_path
        )
    assert "落点" in ei.value.message


# ---------- 指纹不合即拒 ----------

def test_fingerprint_mismatch_rejects_capture(db_path):
    batch = captures.create_batch("站内目录甲", "错列批", db_path)
    # v1 要求 title+code 两列；缺列、串列均属指纹不合
    for bad_payload in ('{"title":"只有标题"}', '{"title":"杯","code":"C-2","price":"9.9"}'):
        with pytest.raises(ServiceError) as ei:
            captures.add_item(batch["id"], f"sku-b-{bad_payload[:4]}", bad_payload, "合格", db_path)
        assert "指纹" in ei.value.message


def test_badge_mapping_number_tangle_rejects(db_path):
    # 落点指向的映射号被删 → 徽标与现行映射号拧花
    with sqlite3.connect(db_path) as raw:
        raw.execute("DELETE FROM field_mappings WHERE mapping_no='MAP-v1'")
        raw.commit()
    batch = captures.create_batch("站内目录甲", "拧花批", db_path)
    with pytest.raises(ServiceError) as ei:
        captures.add_item(
            batch["id"], "sku-t1", '{"title":"茶杯","code":"C-1"}', "合格", db_path
        )
    assert "拧花" in ei.value.message


# ---------- 切版：单事务、串行、只读凭证 ----------

def test_cutover_switches_active_mapping_and_old_pay_load_rejected(db_path):
    landing = mappings.cutover("MAP-v2", "目录舱加列切版", db_path)
    assert landing["is_active"] == 1
    assert landing["mapping_no"] == "MAP-v2"
    assert landing["mapping_key"] == "catalog.v2"
    # 当刻列指纹冻进凭证
    assert landing["column_fingerprint"] == mappings.fingerprint_of(
        mappings.get_mapping("MAP-v2", db_path)["columns_json"]
    )
    # 旧凭证仍在但只读归档，不再现行
    landings = mappings.list_landings(db_path)
    assert len(landings) == 2
    assert sum(1 for r in landings if r["is_active"]) == 1
    old = next(r for r in landings if r["mapping_no"] == "MAP-v1")
    assert old["is_active"] == 0

    gate = mappings.get_gate(db_path)
    assert gate["mapping_no"] == "MAP-v2"
    batch = captures.create_batch("站内目录甲", "切版后批", db_path)
    # 旧映射口径（缺 price）必须拒
    with pytest.raises(ServiceError) as ei:
        captures.add_item(
            batch["id"], "sku-old", '{"title":"旧口径","code":"O-1"}', "合格", db_path
        )
    assert "指纹" in ei.value.message
    # 新映射口径放行，且留痕新映射号与新指纹
    out = captures.add_item(
        batch["id"],
        "sku-new",
        '{"title":"新口径","code":"N-1","price":"9.9"}',
        "合格",
        db_path,
    )
    assert out["quality"] == "合格"
    assert out["mapping_no"] == "MAP-v2"
    assert out["column_fingerprint"] == gate["column_fingerprint"]


def test_cutover_to_unknown_mapping_is_atomic(db_path):
    before = mappings.list_landings(db_path)
    with pytest.raises(ServiceError):
        mappings.cutover("MAP-NOPE", "幻影切版", db_path)
    # 失败后：无新落点、现行凭证不变、无脏审计
    after = mappings.list_landings(db_path)
    assert [dict(r) for r in after] == [dict(r) for r in before]
    assert mappings.get_gate(db_path)["mapping_no"] == "MAP-v1"


def test_concurrent_cutover_only_one_wins(db_path):
    holder = sqlite3.connect(db_path, timeout=1)
    holder.execute("PRAGMA busy_timeout=1000")
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ServiceError) as ei:
            mappings.cutover("MAP-v2", "争抢切版", db_path)
        msg = ei.value.message
        assert "争抢" in msg or "稍后" in msg or "串行" in msg
    finally:
        holder.rollback()
        holder.close()
    win = mappings.cutover("MAP-v2", "串行再切", db_path)
    assert win["is_active"] == 1
    with sqlite3.connect(db_path) as raw:
        active = raw.execute(
            "SELECT COUNT(*) AS c FROM map_cutover_landings WHERE is_active=1"
        ).fetchone()[0]
        rows = raw.execute("SELECT COUNT(*) AS c FROM map_cutover_landings").fetchone()[0]
    assert active == 1
    assert rows == 2


def test_landing_rows_are_read_only_history(db_path):
    first = mappings.get_gate(db_path)["landing_id"]
    mappings.cutover("MAP-v2", "第一次切", db_path)
    mappings.cutover("MAP-v1", "回切", db_path)
    landings = mappings.list_landings(db_path)
    assert len(landings) == 3
    # 历史行不被覆盖：首行仍在且归档只读
    first_row = next(r for r in landings if r["id"] == first)
    assert first_row["is_active"] == 0
    assert first_row["mapping_no"] == "MAP-v1"
    # 服务面不提供改/删落点的能力
    assert not hasattr(mappings, "update_landing")
    assert not hasattr(mappings, "delete_landing")


# ---------- 好件不得打成坏件；主链四处贯通 ----------

def test_good_item_not_downgraded_after_cutover(db_path):
    mappings.cutover("MAP-v2", "加列", db_path)
    batch = captures.create_batch("站内目录乙", "好件批", db_path)
    good = captures.add_item(
        batch["id"],
        "sku-good",
        '{"title":"完整好件","code":"G-1","price":"12.5"}',
        "合格",
        db_path,
    )
    assert good["quality"] == "合格"
    detail = captures.get_batch(batch["id"], db_path)
    item = next(i for i in detail["items"] if i["id"] == good["id"])
    assert item["mapping_no"] == "MAP-v2"
    assert item["column_fingerprint"]


def test_main_chain_with_cutover_stamp_and_review_visibility(db_path):
    mappings.cutover("MAP-v2", "主链切版", db_path)
    batch = captures.create_batch("站内目录甲", "主链批", db_path)
    bad = captures.add_item(
        batch["id"],
        "sku-bad",
        '{"title":"缺价坏件","code":"B-1","price":""}',
        "缺字段",
        db_path,
    )
    assert bad["mapping_no"] == "MAP-v2"
    bins = quarantine.list_bins(db_path)
    open_bin = next(b for b in bins if b["status"] == "开放")
    row = quarantine.enter_item(bad["id"], open_bin["id"], "测试入舱", db_path)
    tickets = review.list_tickets(db_path)
    ticket = next(t for t in tickets if t["row_id"] == row["id"])
    # 复核详情带只读切版口径
    assert ticket["mapping_no"] == "MAP-v2"
    assert ticket["column_fingerprint"]
    decided = review.decide(ticket["id"], "驳回回炉", "tester", "回炉", db_path)
    assert decided["decision"] == "驳回回炉"
    jobs = rework.list_jobs(db_path)
    job = next(j for j in jobs if j["row_id"] == row["id"])
    assert rework.run_job(job["id"], succeed=True, db_path=db_path)["status"] == "成功"
    assert "待复核" in reconcile.run_reconcile(db_path)["summary"]


def test_capture_list_surfaces_current_mapping_number(db_path):
    mappings.cutover("MAP-v2", "列表口径", db_path)
    batches = captures.list_batches(db_path)
    assert all(b["current_mapping_no"] == "MAP-v2" for b in batches)
    gate = mappings.get_gate(db_path)
    assert gate["badge"] == "切版已亮"
    assert gate["mapping_no"] != gate["badge"]  # 徽标与映射号是两个口径，不得混成一个字段
