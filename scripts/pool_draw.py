# -*- coding: utf-8 -*-
"""
pool_draw.py — 情节卡池 + 加权抽卡 + .ydk 导出

设计原则:
  ygo_master.db     = 只读参考资料 (卡库/稀有度/禁限), 永不被跑团逻辑修改
  ygo_campaign.db   = 战役运行时库 (卡池定义/玩家收集/抽卡日志/剧情解锁)

用法:
  python pool_draw.py init                  # 初始化战役库(幂等)
  python pool_draw.py demo                  # 建第一章示例池并抽10包演示
  python pool_draw.py draw <pool_id> <n>    # 从指定池抽 n 包
  python pool_draw.py export <deck_name> <file.ydk>  # 把玩家收藏导出为卡组
"""
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"E:\FUN\YGO-DATA")
MASTER = ROOT / "db" / "ygo_master.db"
CAMPAIGN = ROOT / "db" / "ygo_campaign.db"

# 稀有度 -> 权重 (掉率). 来源参考: pack.db 的 rarity 字段 (N,R,SR,UR,SE,P+...)
RARITY_WEIGHT = {"N": 60, "R": 25, "SR": 10, "UR": 5}
RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "UR": 3}
PITY_LEN = 10          # 连续 N 包无 SR+ -> 保底 SR+
PITY_MIN = "SR"


def campaign_con() -> sqlite3.Connection:
    con = sqlite3.connect(CAMPAIGN)
    con.row_factory = sqlite3.Row
    return con


def init():
    con = campaign_con()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS pools (
        pool_id TEXT PRIMARY KEY,
        name TEXT, chapter INTEGER,
        theme TEXT,             -- 情节主题 (剧情描述, 给AI看)
        tier INTEGER,           -- 强度分档 1-5
        notes TEXT);
    CREATE TABLE IF NOT EXISTS pool_cards (
        pool_id TEXT, id INTEGER,
        rarity TEXT,            -- N/R/SR/UR (卡池内投放稀有度, 可与发行稀有度不同)
        weight REAL DEFAULT 1,  -- 池内权重 (情节偏爱的卡调高)
        unlock_plot TEXT,       -- 非空=剧情解锁卡: 先抽到也无效, 直到该剧情flag置位
        PRIMARY KEY (pool_id, id));
    CREATE TABLE IF NOT EXISTS collection (   -- 玩家收集
        id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0,
        first_from TEXT);       -- 首次获得来源 (池/剧情)
    CREATE TABLE IF NOT EXISTS draw_log (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, pool_id TEXT, id INTEGER,
        rarity TEXT, pity_used INTEGER DEFAULT 0, seed INTEGER);
    CREATE TABLE IF NOT EXISTS plot_flags (
        flag TEXT PRIMARY KEY, value TEXT, set_at TEXT);
    """)
    con.commit()
    print(f"战役库就绪: {CAMPAIGN}")


def register_pool(con, pool_id, name, chapter, theme, tier, card_ids, notes=""):
    """把一批 passcode 注册进池: 稀有度自动取 md_rarity 归一化到 N/R/SR/UR"""
    mcon = sqlite3.connect(MASTER)
    rar = {}
    for cid in card_ids:
        row = mcon.execute("SELECT md_rarity FROM cards_intl WHERE id=?", (cid,)).fetchone()
        if not row or not row[0]:
            continue
        r = str(row[0])
        rar[cid] = "UR" if "Ultra" in r or "Secret" in r or "Prismatic" in r else \
                   "SR" if "Super" in r else \
                   "R" if "Rare" in r else "N"
    mcon.close()
    con.execute("""INSERT OR REPLACE INTO pools VALUES (?,?,?,?,?,?)""",
                (pool_id, name, chapter, theme, tier, notes))
    con.executemany("""INSERT OR REPLACE INTO pool_cards VALUES (?,?,?,?,NULL)""",
                    [(pool_id, c, r, RARITY_WEIGHT[r]) for c, r in rar.items()])
    con.commit()
    return len(rar)


def build_demo_pool():
    """第一章示例池: '青眼的传说' — 白龙主题 + 通用新手魔法陷阱.
    池子由 SQL 从真实卡库筛选 + AI/人工微调, 这里演示纯 SQL 生成."""
    mcon = sqlite3.connect(MASTER)
    # 主题卡: 青眼字段, 非禁限
    theme = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i
        JOIN texts t ON t.id=i.id
        WHERE i.archetype='Blue-Eyes'
          AND i.id NOT IN (SELECT id FROM banlist_current)
          AND t.desc NOT LIKE '%(control this card% Stephan%)'
        LIMIT 40""")]
    # 泛用新手卡: 凡骨向的通用魔陷 (演示: 抽几张经典)
    staples = [r[0] for r in mcon.execute("""
        SELECT id FROM cards_intl WHERE name_en IN (
          'Pot of Greed','Swords of Revealing Light','Dark Hole',
          'Monster Reborn','Trap Hole')""")]
    mcon.close()
    con = campaign_con()
    n1 = register_pool(con, "ch1_dragon", "第一章·青眼的传说", 1,
                       "远古白龙苏醒, 决斗者在遗迹中拾得的龙族卡。", 1, theme,
                       "情节卡池: 只投放青眼字段, 服务第一章剧情")
    n2 = register_pool(con, "ch1_staple", "第一章·遗迹的常识", 1,
                       "遗迹中的通用魔陷, 教学用泛用卡。", 1, staples,
                       "情节卡池: 教学泛用")
    print(f"池注册完成: ch1_dragon {n1} 张, ch1_staple {n2} 张")


def draw_pack(pool_ids, seed=None):
    """抽一包: 每包 3 张, 稀有度保底: 1 张 R+, 0-2 张 N.
    剧情解锁卡 (unlock_plot 非空且flag未置位) 抽中时记为'沉睡', 不入收藏."""
    rng = random.Random(seed)
    con = campaign_con()
    holders = []
    for pid in pool_ids:
        holders += con.execute("""SELECT pc.id, pc.rarity, pc.weight, pc.unlock_plot
            FROM pool_cards pc WHERE pc.pool_id=?""", (pid,)).fetchall()
    if not holders:
        return []

    def pick():
        total = sum(h["weight"] for h in holders)
        x = rng.uniform(0, total)
        for h in holders:
            x -= h["weight"]
            if x <= 0:
                return h
        return holders[-1]

    picked = [pick() for _ in range(3)]
    forced = max(range(3), key=lambda i: RARITY_ORDER[picked[i]["rarity"]])
    if RARITY_ORDER[picked[forced]["rarity"]] < RARITY_ORDER["R"]:
        r_plus = [h for h in holders if RARITY_ORDER[h["rarity"]] >= RARITY_ORDER["R"]]
        if r_plus:
            picked[forced] = rng.choice(r_plus)   # 保底: 至少一张 R+
    return picked


def cmd_draw(pool_ids, packs, seed=None):
    con = campaign_con()
    got = {}
    for i in range(packs):
        s = None if seed is None else seed + i
        for h in draw_pack(pool_ids, seed=s):
            cid = h["id"]
            asleep = h["unlock_plot"] and not con.execute(
                "SELECT 1 FROM plot_flags WHERE flag=?", (h["unlock_plot"],)).fetchone()
            status = "asleep" if asleep else "got"
            got.setdefault(cid, {"rarity": h["rarity"], "n": 0, "status": status})
            if not asleep:
                got[cid]["n"] += 1
                con.execute("""INSERT INTO collection(id,count,first_from)
                    VALUES (?,1,?) ON CONFLICT(id) DO UPDATE SET count=count+1""",
                    (cid, f"pool:{'+'.join(pool_ids)}"))
            con.execute("INSERT INTO draw_log(pool_id,id,rarity,seed) VALUES (?,?,?,?)",
                        ("+".join(pool_ids), cid, h["rarity"], s))
    con.commit()
    mcon = sqlite3.connect(MASTER)
    print(f"{'卡名(中文)':<24}{'英文名':<34}稀有度  入手")
    for cid, g in sorted(got.items(), key=lambda kv: -RARITY_ORDER[kv[1]["rarity"]]):
        nm = mcon.execute("SELECT name FROM texts WHERE id=?", (cid,)).fetchone()
        en = mcon.execute("SELECT name_en FROM cards_intl WHERE id=?", (cid,)).fetchone()
        mark = "(剧情锁定·沉睡)" if g["status"] == "asleep" else f"x{g['n']}"
        print(f"{(nm[0] if nm else cid):<24}{(en[0] if en else '-'):<34}{g['rarity']:<6}  {mark}")


def cmd_export(name, out_path):
    """从玩家收藏导出 .ydk: 自动组卡(N枚主题卡优先), 也可导出指定passcode清单.
    简化版: 收藏全部塞主卡组(上限40), 额外卡组按类型分流."""
    con = campaign_con()
    mcon = sqlite3.connect(MASTER)
    main, extra = [], []
    for row in con.execute("SELECT id, count FROM collection ORDER BY count DESC"):
        cid = row["id"]
        t = mcon.execute("SELECT type FROM cards_intl WHERE id=?", (cid,)).fetchone()
        if not t:
            continue
        bucket = extra if ("Fusion" in t[0] or "Synchro" in t[0] or "Xyz" in t[0]
                           or "Link" in t[0]) else main
        bucket += [cid] * min(row["count"], 3)
    main, extra = main[:40], extra[:15]
    ydk = "#created by pool_draw\n#main\n" + "\n".join(map(str, main)) + \
          "\n#extra\n" + "\n".join(map(str, extra)) + "\n!side\n"
    Path(out_path).write_text(ydk, encoding="utf-8")
    print(f"导出 {name}: 主{len(main)} 额外{len(extra)} -> {out_path}")


# ============================================================
# MD 风格开包 + 收藏库 + 技能注册 (campaign_library 扩展)
# ============================================================

RARITY_NAME = {"N": "普通", "R": "稀有", "SR": "超稀有", "UR": "究极稀有"}
PACK_SIZE = 6          # 每包6张: 5普通槽+1稀有槽
SR_CHANCE = 20         # 稀有槽 1/20 出 SR
UR_CHANCE = 100        # 稀有槽 1/100 出 UR
PITY_PACKS = 10        # 连开10包无SR+ -> 下一包必出SR+


def pack_open(con, pool_ids, packs, owner="player"):
    """开包: 每包5普通+1稀有(可升SR/UR), 大保底计数, 写入收藏"""
    results = []
    try:
        row = con.execute("SELECT value FROM meta_pack WHERE key='pity'").fetchone()
        pity_n = int(row[0]) if row else 0
    except Exception:
        con.execute("CREATE TABLE IF NOT EXISTS meta_pack(key TEXT PRIMARY KEY, value TEXT)")
        pity_n = 0
    for pn in range(packs):
        pack = []
        force_sr = (pity_n + 1) >= PITY_PACKS
        # 5 普通槽
        for _ in range(5):
            pack.append(_pick_weighted(con, pool_ids, max_rarity="R"))
        # 1 稀有槽
        rare = _pick_weighted(con, pool_ids, max_rarity="R")
        roll = con.execute("SELECT 1").fetchone() and __import__("random").randint(1, UR_CHANCE)
        if roll == 1:
            rare = _pick_weighted(con, pool_ids, min_rarity="UR")
        elif roll <= SR_CHANCE:
            rare = _pick_weighted(con, pool_ids, min_rarity="SR")
        if force_sr and RARITY_ORDER.get(rare[1], 0) < RARITY_ORDER["SR"]:
            rare = _pick_weighted(con, pool_ids, min_rarity="SR")
        pack.append(rare)
        # 入库
        has_sr = False
        for cid, rar in pack:
            con.execute("""INSERT INTO collection(id,count,first_from) VALUES(?,1,?)
                ON CONFLICT(id) DO UPDATE SET count=count+1""", (cid, f"pack:{'+'.join(pool_ids)}"))
            if RARITY_ORDER.get(rar, 0) >= RARITY_ORDER["SR"]:
                has_sr = True
            con.execute("INSERT INTO draw_log(pool_id,id,rarity,seed) VALUES(?,?,?,?)",
                        ("+".join(pool_ids), cid, rar, pn))
        results.append(pack)
        pity_n = 0 if has_sr else pity_n + 1
    con.execute("CREATE TABLE IF NOT EXISTS meta_pack(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta_pack VALUES('pity',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(pity_n),))
    con.commit()
    return results


def _pick_weighted(con, pool_ids, min_rarity=None, max_rarity=None):
    """按稀有度区间加权抽一张 (基于 pack_cards 权重与投放稀有度)"""
    import random as _r
    ph = ",".join("?" * len(pool_ids))
    rows = con.execute(
        f"SELECT id, rarity, weight FROM pool_cards WHERE pool_id IN ({ph})",
        pool_ids).fetchall()
    if not rows:
        return (0, "N")
    def ok(r):
        v = RARITY_ORDER.get(r, 0)
        if min_rarity and v < RARITY_ORDER[min_rarity]:
            return False
        if max_rarity and v > RARITY_ORDER[max_rarity]:
            return False
        return True
    cand = [r for r in rows if ok(r[1])] or rows
    total = sum(r[2] for r in cand)
    x = _r.uniform(0, total)
    for r in cand:
        x -= r[2]
        if x <= 0:
            return (r[0], r[1])
    return (cand[-1][0], cand[-1][1])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        init()
    elif cmd == "demo":
        init()
        build_demo_pool()
        print("\n== 抽 10 包 (ch1_dragon+ch1_staple) ==")
        cmd_draw(["ch1_dragon", "ch1_staple"], 10, seed=2026)
        print("\n== 导出卡组 ==")
        cmd_export("新手指卡组", str(ROOT / "db" / "starter_demo.ydk"))
    elif cmd == "draw":
        cmd_draw(sys.argv[2].split("+"), int(sys.argv[3]))
    elif cmd == "export":
        cmd_export(sys.argv[2], sys.argv[3])
    elif cmd == "pack":
        pools = sys.argv[2].split("+")
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        con = campaign_con()
        init()
        res = pack_open(con, pools, n)
        m = sqlite3.connect(str(MASTER))
        for i, pack in enumerate(res, 1):
            print(f"--- 第{i}包 ---")
            for cid, rar in pack:
                nm = m.execute("SELECT name FROM texts WHERE id=?", (cid,)).fetchone()
                print(f"  [{RARITY_NAME.get(rar, rar)}] {nm[0] if nm else cid}")
    elif cmd == "collection":
        con = campaign_con()
        mdb = sqlite3.connect(str(MASTER))
        rows = con.execute(
            "SELECT id, count FROM collection ORDER BY count DESC, id").fetchall()
        print(f"收藏共 {len(rows)} 种:")
        for cid, cnt in rows:
            nm = mdb.execute("SELECT name FROM texts WHERE id=?", (cid,)).fetchone()
            print(f"  x{cnt:<3} {nm[0] if nm else cid}")
    elif cmd == "build":
        # build <文件.ydk> : 从收藏组卡 (每卡最多3张, 主≤40 额外≤15)
        out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "db" / "collection_deck.ydk")
        con = campaign_con()
        rows = con.execute("SELECT id, MIN(count,3) AS n FROM collection ORDER BY id").fetchall()
        m = sqlite3.connect(str(MASTER))
        main_cards, extra_cards = [], []
        for cid, n in rows:
            t = m.execute("SELECT type FROM cards_intl WHERE id=?", (cid,)).fetchone()
            bucket = extra_cards if t and any(k in (t[0] or "") for k in ("Fusion", "Synchro", "Xyz", "Link")) else main_cards
            bucket += [cid] * n
        NL = chr(10)
        content = ("#created by campaign collection" + NL + "#main" + NL +
                   NL.join(map(str, main_cards[:40])) + NL +
                   "#extra" + NL + NL.join(map(str, extra_cards[:15])) + NL +
                   "!side" + NL)
        Path(out).write_text(content, encoding="utf-8")
        print(f"从收藏组卡: 主{len(main_cards[:40])} 额外{len(extra_cards[:15])} -> {out}")


