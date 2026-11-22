"""字段映射切版（甲路：冻凭证表 / 只读切版落点）。

口径：
- field_mappings 是映射目录，map_cutover_landings 是只读切版凭证（落点）。
- 切版在单事务内完成：旧落点全部归档 → 冻当刻映射键与列指纹 → 新落点钉现行。
- 同一切版行的争抢由写锁串行化，锁不到就白话报错，绝不互相盖掉。
- 采集闸只认现行落点：无落点、徽标与映射号拧花、列指纹不合一律拒采集，
  不允许静默沿旧映射。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from app.db import get_db
from app.services.errors import ServiceError

CUTOVER_BADGE_KEY = "map_cutover_badge"
CUTOVER_BADGE = "切版已亮"


def fingerprint_of(columns_json: str) -> str:
    """列指纹：按列名排序的 sha256 前 16 位，载荷列集合须完全一致。"""
    try:
        cols = json.loads(columns_json)
    except (TypeError, ValueError):
        cols = []
    if not isinstance(cols, list) or not all(isinstance(c, str) and c for c in cols):
        raise ServiceError("映射列定义不合法，无法生成指纹")
    norm = sorted(set(cols))
    return "fp-" + hashlib.sha256("|".join(norm).encode("utf-8")).hexdigest()[:16]


def payload_fingerprint(payload: str) -> str:
    try:
        data = json.loads(payload or "{}")
    except (TypeError, ValueError):
        raise ServiceError("抓取载荷不是合法 JSON，列指纹无法核验")
    if not isinstance(data, dict):
        raise ServiceError("抓取载荷结构不合，列指纹无法核验")
    return fingerprint_of(json.dumps(sorted(data.keys()), ensure_ascii=False))


def list_mappings(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM field_mappings ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_mapping(mapping_no: str, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM field_mappings WHERE mapping_no=?", (mapping_no,)
        ).fetchone()
        if not row:
            raise ServiceError(f"映射号 {mapping_no} 不存在")
        return dict(row)


def list_landings(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM map_cutover_landings ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_gate(db_path: str | None = None) -> dict:
    """现行采集闸口径：徽标、现行映射号、落点、指纹四者对齐才放行。"""
    with get_db(db_path) as conn:
        badge_row = conn.execute(
            "SELECT value FROM meta WHERE key=?", (CUTOVER_BADGE_KEY,)
        ).fetchone()
        badge = badge_row["value"] if badge_row else ""
        landing = conn.execute(
            "SELECT * FROM map_cutover_landings WHERE is_active=1"
        ).fetchone()
        if not landing:
            return {
                "aligned": False,
                "badge": badge,
                "mapping_no": "",
                "mapping_key": "",
                "landing_id": 0,
                "column_fingerprint": "",
                "reason": "无切版落点，禁止沿旧映射采集",
            }
        mapping = conn.execute(
            "SELECT * FROM field_mappings WHERE mapping_no=?",
            (landing["mapping_no"],),
        ).fetchone()
        if not mapping:
            return {
                "aligned": False,
                "badge": badge,
                "mapping_no": landing["mapping_no"],
                "mapping_key": landing["mapping_key"],
                "landing_id": landing["id"],
                "column_fingerprint": landing["column_fingerprint"],
                "reason": "切版徽标与现行映射号拧花，禁止采集",
            }
        fp_ok = mapping["column_fingerprint"] == landing["column_fingerprint"]
        aligned = bool(badge) and fp_ok
        return {
            "aligned": aligned,
            "badge": badge,
            "mapping_no": mapping["mapping_no"],
            "mapping_key": mapping["mapping_key"],
            "landing_id": landing["id"],
            "column_fingerprint": landing["column_fingerprint"],
            "reason": "" if aligned else "列指纹与切版凭证不合，禁止采集",
        }


def require_gate(db_path: str | None = None) -> dict:
    gate = get_gate(db_path)
    if not gate["aligned"]:
        raise ServiceError(gate["reason"] or "切版口径未对齐，禁止采集", 409)
    return gate


def verify_payload(payload: str, db_path: str | None = None) -> dict:
    """采集闸：无落点拒、拧花拒、载荷列指纹不合拒。返回当刻留痕口径。"""
    gate = require_gate(db_path)
    if payload_fingerprint(payload) != gate["column_fingerprint"]:
        raise ServiceError(
            f"抓取列指纹与现行映射 {gate['mapping_no']} 不合，禁止写入，"
            "请按切版后列结构重抓",
            409,
        )
    return gate


def cutover(mapping_no: str, reason: str = "", db_path: str | None = None) -> dict:
    """串行单事务切版：归档旧落点、冻新凭证、亮徽标，失败整体回滚并吐白话。

    get_db 在异常时回滚、正常退出时提交，故本函数内所有写操作天然同事务；
    BEGIN IMMEDIATE 只用于抢先拿写锁，让两侧同抢快速失败而非互相盖掉。
    """
    mapping_no = (mapping_no or "").strip()
    reason = (reason or "").strip() or "映射切版"
    with get_db(db_path) as conn:
        # 切版争抢立即失败、不排队：由调用方重试，避免两侧互相盖钉点
        conn.execute("PRAGMA busy_timeout=0")
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise ServiceError(
                "另一侧切版正在占用同一映射行，请稍后重试，本次未改动任何落点", 409
            ) from exc
        mapping = conn.execute(
            "SELECT * FROM field_mappings WHERE mapping_no=?", (mapping_no,)
        ).fetchone()
        if not mapping:
            raise ServiceError(f"映射号 {mapping_no} 不存在，切版已整体回滚")
        fp = fingerprint_of(mapping["columns_json"])
        if fp != mapping["column_fingerprint"]:
            raise ServiceError(
                f"映射 {mapping_no} 列指纹自校验不合，切版已整体回滚"
            )
        conn.execute(
            "UPDATE map_cutover_landings SET is_active=0 WHERE is_active=1"
        )
        cur = conn.execute(
            """
            INSERT INTO map_cutover_landings(
              mapping_no, mapping_key, column_fingerprint, reason, is_active
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (
                mapping["mapping_no"],
                mapping["mapping_key"],
                fp,
                reason,
            ),
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (CUTOVER_BADGE_KEY, CUTOVER_BADGE),
        )
        conn.execute(
            """
            INSERT INTO audit_events(actor, action, entity_type, entity_id, detail)
            VALUES ('admin', '映射切版', 'field_mapping', ?, ?)
            """,
            (
                mapping["id"],
                f"{mapping['mapping_no']} 落点#{cur.lastrowid} 指纹{fp} {reason}",
            ),
        )
        landing_id = cur.lastrowid
    return get_landing(landing_id, db_path)


def get_landing(landing_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM map_cutover_landings WHERE id=?", (landing_id,)
        ).fetchone()
        if not row:
            raise ServiceError("切版落点不存在", 404)
        return dict(row)


def gate_summary(db_path: str | None = None) -> dict:
    gate = get_gate(db_path)
    with get_db(db_path) as conn:
        landings = conn.execute(
            "SELECT COUNT(*) AS c FROM map_cutover_landings"
        ).fetchone()["c"]
        mappings_total = conn.execute(
            "SELECT COUNT(*) AS c FROM field_mappings"
        ).fetchone()["c"]
    return {
        **gate,
        "landing_count": landings,
        "mapping_count": mappings_total,
    }
