# -*- coding: utf-8 -*-
"""
build_master_db.py — 把多路数据源合成 E:/FUN/YGO-DATA/db/ygo_master.db

数据源:
  db/cards_zh.cdb        MDPro3 中文卡库 (datas + texts, 14505 张, ygopro 标准 schema)
  db/pack_reference.db   MDPro3 pack.db  (卡ID -> 日文卡包 -> 稀有度 -> 发售日)
  sources/raw/cardinfo_full.json    YGOPRODECK 全量国际数据 (英文名/字段/卡组/禁限/md_rarity)
  sources/raw/cardsets.json         YGOPRODECK 卡包系列列表
  sources/raw/archetypes.json       YGOPRODECK 字段(archetype)列表
  sources/lflist.conf               ygopro 禁限卡表 (多日期分区)

产出 ygo_master.db 表:
  datas, texts          中文卡库 (原样)
  cards_intl            国际数据按 passcode 对齐 (英文名/描述/数值/archetype/禁限/md_rarity/日期)
  card_in_sets          每张卡的 TCG 收录 (卡包+稀有度+价格)
  card_sets_info        卡包系列总表
  archetypes            字段列表
  card_packs_jp         日文卡包收录 (id, pack_id, pack, rarity, date)
  banlist_current       最新一期禁限表
  card_tags             空表: AI 批量打标用 (strategy/archetype_role/teaching/difficulty)
  meta                  数据来源与版本
"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"E:\FUN\YGO-DATA")
DB = ROOT / "db" / "ygo_master.db"
RAW = ROOT / "sources" / "raw"

def main():
    shutil.copyfile(ROOT / "db" / "cards_zh.cdb", DB)
    con = sqlite3.connect(DB)
    con.execute("ATTACH ? AS src", (str(ROOT / "db" / "pack_reference.db"),))

    # ---- 1. 日文卡包收录表 ----
    con.execute("DROP TABLE IF EXISTS card_packs_jp")
    con.execute("""CREATE TABLE card_packs_jp (
        id INTEGER, pack_id TEXT, pack TEXT, rarity TEXT, date TEXT)""")
    con.execute("INSERT INTO card_packs_jp SELECT id, pack_id, pack, rarity, date FROM src.pack")
    con.commit()

    # ---- 2. 国际数据 ----
    info = json.loads((RAW / "cardinfo_full.json").read_text(encoding="utf-8"))
    cards = info["data"]
    con.execute("DROP TABLE IF EXISTS cards_intl")
    con.execute("""CREATE TABLE cards_intl (
        id INTEGER PRIMARY KEY, konami_id INTEGER, name_en TEXT, type TEXT, frame_type TEXT,
        desc_en TEXT, atk INTEGER, def INTEGER, level INTEGER, race TEXT, attribute TEXT,
        archetype TEXT, linkval INTEGER, scale INTEGER,
        ban_tcg TEXT, ban_ocg TEXT, ban_goat TEXT,
        md_rarity TEXT, tcg_date TEXT, ocg_date TEXT, has_effect INTEGER,
        ygoprodeck_url TEXT)""")
    con.execute("DROP TABLE IF EXISTS card_in_sets")
    con.execute("""CREATE TABLE card_in_sets (
        id INTEGER, set_name TEXT, set_code TEXT, set_rarity TEXT, set_price TEXT)""")
    for c in cards:
        ban = c.get("banlist_info", {}) or {}
        misc = c.get("misc_info", [{}])
        m = misc[0] if misc else {}
        con.execute("INSERT OR REPLACE INTO cards_intl VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["id"], m.get("konami_id"), c.get("name"), c.get("type"), c.get("frameType"),
             c.get("desc"), c.get("atk"), c.get("def"), c.get("level"), c.get("race"),
             c.get("attribute"), c.get("archetype"), c.get("linkval"), c.get("scale"),
             ban.get("ban_tcg"), ban.get("ban_ocg"), ban.get("ban_goat"),
             m.get("md_rarity"), m.get("tcg_date"), m.get("ocg_date"),
             1 if m.get("has_effect") else 0, c.get("ygoprodeck_url")))
        for s in c.get("card_sets", []) or []:
            con.execute("INSERT INTO card_in_sets VALUES (?,?,?,?,?)",
                (c["id"], s.get("set_name"), s.get("set_code"), s.get("set_rarity"), s.get("set_price")))
    con.commit()

    # ---- 3. 卡包系列 / 字段 ----
    sets = json.loads((RAW / "cardsets.json").read_text(encoding="utf-8"))
    con.execute("DROP TABLE IF EXISTS card_sets_info")
    con.execute("""CREATE TABLE card_sets_info (
        set_code TEXT PRIMARY KEY, set_name TEXT, num_of_cards INTEGER, tcg_date TEXT)""")
    for s in sets:
        con.execute("INSERT OR REPLACE INTO card_sets_info VALUES (?,?,?,?)",
            (s.get("set_code"), s.get("set_name"), s.get("num_of_cards"), s.get("tcg_date")))

    archs = json.loads((RAW / "archetypes.json").read_text(encoding="utf-8"))
    con.execute("DROP TABLE IF EXISTS archetypes")
    con.execute("CREATE TABLE archetypes (archetype_name TEXT PRIMARY KEY)")
    con.executemany("INSERT OR REPLACE INTO archetypes VALUES (?)",
        [(a["archetype_name"],) for a in archs])
    con.commit()

    # ---- 4. 禁限表: MDPro3 lflist.conf 格式
    #   !2026.1            -> 分区名(文件中第一个分区即当前生效表)
    #   #forbidden/#limited/#semi-limited -> 其后的卡状态
    #   20292186 0 --卡片名  -> 卡行
    text = (ROOT / "sources" / "lflist.conf").read_text(encoding="utf-8", errors="replace")
    status_map = {"forbidden": "禁止", "limited": "限制", "semi-limited": "准限制",
                  "ban": "禁止", "semi_limited": "准限制"}
    sections, cur_section, cur_status = [], None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#["):
            continue
        if line.startswith("!"):            # 分区名
            cur_section = line[1:].strip()
            cur_status = None
            continue
        m = re.match(r"#\s*(\S+)", line)
        if m and m.group(1).lower() in status_map:
            cur_status = status_map[m.group(1).lower()]
            continue
        m = re.match(r"^(\d{8,})\s+(-?\d+)", line)
        if m and cur_section and cur_status:
            sections.append((cur_section, int(m.group(1)), cur_status, int(m.group(2))))
    if not sections:
        raise SystemExit("lflist.conf 解析失败: 未找到任何条目")
    latest = sections[0][0]
    con.execute("DROP TABLE IF EXISTS banlist_current")
    con.execute("""CREATE TABLE banlist_current (
        id INTEGER PRIMARY KEY, status TEXT, count INTEGER, list_date TEXT)""")
    con.executemany("INSERT OR REPLACE INTO banlist_current VALUES (?,?,?,?)",
        [(cid, st, cnt, d) for (d, cid, st, cnt) in sections if d == latest])
    con.execute("DROP TABLE IF EXISTS banlist_history")
    con.execute("""CREATE TABLE banlist_history (
        list_name TEXT, id INTEGER, status TEXT, count INTEGER)""")
    con.executemany("INSERT INTO banlist_history VALUES (?,?,?,?)", sections)
    con.commit()

    # ---- 5. AI 打标表 (空) ----
    con.execute("DROP TABLE IF EXISTS card_tags")
    con.execute("""CREATE TABLE card_tags (
        id INTEGER PRIMARY KEY,
        strategy TEXT,          -- 展开点/干扰/斩杀/回收/过牌/ pivot ...
        archetype_role TEXT,    -- 核心/辅助/泛用
        teaching_memo TEXT,     -- 演示什么机制, 适合哪章教学
        pool_tier INTEGER,      -- 卡池强度分档 1-5
        notes TEXT)""")

    # ---- 6. 出处 ----
    dbver = json.loads((RAW / "checkdbver.json").read_text(encoding="utf-8")) \
        if (RAW / "checkdbver.json").exists() else [{"database_version": "unknown"}]
    con.execute("DROP TABLE IF EXISTS meta")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    meta_rows = [
        ("ygoprodeck_db_version", dbver[0].get("database_version", "")),
        ("ygoprodeck_last_update", dbver[0].get("last_update", "")),
        ("cards_zh_rows", str(con.execute("SELECT COUNT(*) FROM datas").fetchone()[0])),
        ("cards_intl_rows", str(con.execute("SELECT COUNT(*) FROM cards_intl").fetchone()[0])),
        ("card_in_sets_rows", str(con.execute("SELECT COUNT(*) FROM card_in_sets").fetchone()[0])),
        ("card_packs_jp_rows", str(con.execute("SELECT COUNT(*) FROM card_packs_jp").fetchone()[0])),
        ("banlist_date", latest),
        ("source_mdpro3", "E:/FUN/YGO-RPG/YGO/MDPro3 (Data/locales/zh-CN/cards.cdb, Data/pack/pack.db, Data/lflist.conf)"),
    ]
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", meta_rows)
    con.commit()

    # ---- 汇报 ----
    print("== ygo_master.db 构建完成 ==")
    for t in ("datas", "texts", "cards_intl", "card_in_sets", "card_sets_info",
              "archetypes", "card_packs_jp", "banlist_current", "card_tags", "meta"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:18s} {n:>7} 行")
    n_join = con.execute("""SELECT COUNT(*) FROM datas d JOIN cards_intl i ON d.id=i.id""").fetchone()[0]
    n_all = con.execute("SELECT COUNT(*) FROM datas").fetchone()[0]
    print(f"\n中文库与国际库按 passcode 对齐: {n_join}/{n_all}")
    sample = con.execute("""SELECT t.name, t.desc, i.archetype, i.ban_tcg, i.md_rarity
        FROM texts t JOIN cards_intl i ON t.id=i.id WHERE i.archetype='Blue-Eyes' LIMIT 3""").fetchall()
    for row in sample:
        print(" ", row)
    con.close()

if __name__ == "__main__":
    sys.exit(main())
