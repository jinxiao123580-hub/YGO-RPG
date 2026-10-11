# -*- coding: utf-8 -*-
"""
build_ch1_content.py — 生成《决斗者遗迹》第一章的全部内容资产

产出:
  db/ygo_campaign.db      正式版第一章卡池(带权重/沉睡标记) + 剧情flag
  content/npc_decks/*.ydk  3 份 NPC 卡组 (从真实卡库生成, 禁限表合规)
  content/decks/player_starter.ydk  玩家初始卡组 (40张, 店主赠卡设定)
校验: passcode 全部存在于主库, 张数 ≤ min(3, 禁限表允许), 主卡组 ≥40
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(r"E:\FUN\YGO-DATA")
MASTER = ROOT / "db" / "ygo_master.db"
sys_path = ROOT / "scripts"
import sys
sys.path.insert(0, str(sys_path))
from pool_draw import init, register_pool, campaign_con

EXTRA_TYPES = ("Fusion", "Synchro", "Xyz", "Link", "Ritual")


def allowed_count(mcon, cid):
    """当前禁限表允许的张数(默认3)"""
    row = mcon.execute("SELECT status, count FROM banlist_current WHERE id=?", (cid,)).fetchone()
    if not row:
        return 3
    return row["count"]


def legal_copies(mcon, cid, want=3):
    return max(0, min(want, allowed_count(mcon, cid)))


def build_pools():
    mcon = sqlite3.connect(MASTER)
    # datas.type 位掩码 (ygopro): MONSTER=0x1 SPELL=0x2 TRAP=0x4 NORMAL=0x10 EFFECT=0x20
    #   FUSION=0x40 RITUAL=0x80 TUNER=0x1000 SYNCHRO=0x2000 XYZ=0x800000 LINK=0x4000000
    TYPEVAL = {"Ritual": 0x80, "Fusion": 0x40, "Synchro": 0x2000, "Xyz": 0x800000, "Link": 0x4000000}
    mask = 0
    for t in EXTRA_TYPES:
        mask |= TYPEVAL[t]
    # 第一章池: 青眼字段 + 非禁限 + 非额外/仪式 (教学纯度), 青眼白龙排除(剧情发放)
    ids = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.archetype='Blue-Eyes'
          AND i.id NOT IN (SELECT id FROM banlist_current)
          AND i.id != 89631139
          AND (d.type & ?) = 0""", (mask,))]
    staples = [r[0] for r in mcon.execute("""
        SELECT id FROM cards_intl WHERE name_en IN (
          'Swords of Revealing Light','Trap Hole','Fissure','Ookazi',
          'Reinforcement of the Army','Mystical Space Typhoon')""")]
    mcon.close()
    con = campaign_con()
    n1 = register_pool(con, "ch1_pool_dragon", "第一章·白龙的遗产", 1,
                       "旧货店白龙卡的共鸣。只投放召唤法入门卡(无仪式/融合/同调/超量/连接)。",
                       1, ids, "青眼白龙不在池中, 由剧情发放")
    n2 = register_pool(con, "ch1_pool_staple", "第一章·磨坊的赠品", 1,
                       "店主的旧藏通用魔陷, 教学用。", 1, staples)
    flags = {"ch1_cleared": None, "met_xiao": None, "awakening_25": None,
             "ch2_cleared": None, "guardian_defeated": None}
    for f in flags:
        con.execute("INSERT OR IGNORE INTO plot_flags VALUES (?,NULL,NULL)", (f,))
    con.commit()
    print(f"[卡池] ch1_pool_dragon={n1}张 ch1_pool_staple={n2}张, flag初始化={len(flags)}")


def write_deck(path, entries, note):
    lines = ["#created by build_ch1_content", f"#{note}", "#main"]
    main = []
    for cid, n in entries:
        main += [str(cid)] * n
    extra = []
    Path(path).write_text("\n".join(lines + main) + ("\n#extra\n" + "\n".join(map(str, extra)) if extra else "") + "\n!side\n", encoding="utf-8")
    return len(main), len(extra)


def build_npc_decks():
    mcon = sqlite3.connect(MASTER)
    decks = {}

    # 店主·磨坊: 天使族凡骨+悠悠系, 最弱教学卡组
    ids = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.race LIKE '%Fairy%' AND i.frame_type='normal'
          AND (i.id & 0) = 0 AND i.id NOT IN (SELECT id FROM banlist_current)
        ORDER BY i.level LIMIT 14""")]
    decks["npc_miller"] = ([(c, legal_copies(mcon, c)) for c in ids], "店主磨坊: 天使凡骨教学卡组")

    # 门卫·巨石: 岩石族凡骨+守备向
    ids = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.race LIKE '%Rock%' AND i.frame_type='normal'
          AND i.id NOT IN (SELECT id FROM banlist_current)
        ORDER BY i.level LIMIT 14""")]
    decks["npc_guardian"] = ([(c, legal_copies(mcon, c)) for c in ids], "门卫巨石: 岩石凡骨守备卡组")

    # 谜之少年晓: 青眼低配(无额外)
    ids = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.archetype='Blue-Eyes' AND (d.type & ?) = 0
          AND i.id NOT IN (SELECT id FROM banlist_current)
        LIMIT 14""", (sum({"Ritual": 0x80, "Fusion": 0x40, "Synchro": 0x2000, "Xyz": 0x800000, "Link": 0x4000000}[t] for t in EXTRA_TYPES),))]
    decks["npc_xiao"] = ([(c, legal_copies(mcon, c)) for c in ids], "谜之少年晓: 青眼低配(无额外)")

    # 玩家初始卡组: 白龙x1 + 低星凡骨x24 + 经典魔陷x15
    starter = [(89631139, legal_copies(mcon, 89631139, 1))]
    low = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.frame_type='normal' AND i.level<=4
          AND i.id NOT IN (SELECT id FROM banlist_current)
        ORDER BY RANDOM() LIMIT 24""")]
    starter += [(c, legal_copies(mcon, c)) for c in low]
    clas = [r[0] for r in mcon.execute("""
        SELECT id FROM cards_intl WHERE name_en IN (
          'Swords of Revealing Light','Fissure','Trap Hole','Ookazi',
          'Stop Defense','Change of Heart','Dark Hole','Monster Reborn',
          'Remove Trap','De-Spell','Yami','Mountain')""")]
    starter += [(c, legal_copies(mcon, c)) for c in clas]

    # 收缩到恰好 40 张 (从最大叠开始删)
    while sum(n for _, n in starter) > 40:
        starter.sort(key=lambda e: -e[1])
        c, n = starter[0]
        starter[0] = (c, n - 1)
    starter = [e for e in starter if e[1] > 0]
    # 确保白龙仍在 (上面排序删除不会动它, 因为它只有1张)
    assert any(c == 89631139 for c, _ in starter), "青眼白龙必须保留在初始卡组"

    out = ROOT / "content" / "decks"
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for name, (entries, note) in decks.items():
        total = sum(n for _, n in entries)
        # 不足40张时补普通怪兽
        if total < 40:
            fill = [r[0] for r in mcon.execute("""
                SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
                WHERE i.frame_type='normal'
                  AND i.id NOT IN (SELECT id FROM banlist_current)
                ORDER BY RANDOM() LIMIT 30""")]
            for c in fill:
                n = legal_copies(mcon, c)
                while n > 0 and sum(x for _, x in entries) < 40:
                    entries.append((c, 1)); n -= 1
                if sum(x for _, x in entries) >= 40:
                    break
        nm, ne = write_deck(out / f"{name}.ydk", entries, note)
        report.append((name, nm, ne))
    nm, ne = write_deck(out / "player_starter.ydk", starter, "玩家初始卡组: 磨坊的赠品+沉睡白龙")
    report.append(("player_starter", nm, ne))

    # ---- 校验 ----
    ok = True
    for name, nm, ne in report:
        lines = (out / f"{name}.ydk").read_text().splitlines()
        main_lines, section = [], None
        for l in lines:
            l = l.strip()
            if l.startswith("#") or not l:
                continue
            if l in ("!side", "#extra"):
                section = "skip"
                continue
            if l == "#main":
                section = "main"
                continue
            if section == "main":
                main_lines.append(l)
        deck = [int(x) for x in main_lines]
        bad = [c for c in deck if not mcon.execute("SELECT 1 FROM datas WHERE id=?", (c,)).fetchone()]
        counts = {}
        for c in deck:
            counts[c] = counts.get(c, 0) + 1
        over = {c: n for c, n in counts.items() if n > legal_copies(mcon, c)}
        status = "OK " if (not bad and not over and nm >= 40) else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[卡组] {status} {name}: 主{nm} 额外{ne} 缺失{len(bad)} 超限{len(over)}")
    mcon.close()
    return ok


def main():
    init()
    build_pools()
    if not build_npc_decks():
        print("!! 存在校验失败")
        return 1
    print("\n== 第一章内容资产就绪 ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
