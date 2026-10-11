# -*- coding: utf-8 -*-
"""
build_ch2_content.py — 第二章《石之门》内容资产

产出:
  db/ygo_campaign.db  ch2_pool_rock   岩石/守备主题池 (门卫巨石领域, 上级怪兽为主)
                      ch2_pool_staple 上级召唤教学泛用卡
校验: 非禁限, 排除额外/仪式卡组类型, 上级怪兽(5-7星)占比检查
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"E:\FUN\YGO-DATA")
MASTER = ROOT / "db" / "ygo_master.db"
sys.path.insert(0, str(ROOT / "scripts"))
from pool_draw import init, register_pool, campaign_con

EXTRA_MASK = 0x80 | 0x40 | 0x2000 | 0x800000 | 0x4000000  # 仪式/融合/同调/超量/连接


def legal_copies(mcon, cid):
    row = mcon.execute("SELECT count FROM banlist_current WHERE id=?", (cid,)).fetchone()
    return 3 if not row else max(0, min(3, row[0]))


def main():
    init()
    mcon = sqlite3.connect(MASTER)

    # 池1: 岩石族怪兽(含上级) + 非禁限 + 非额外/仪式 —— 门卫巨石的领域
    rock = [r[0] for r in mcon.execute("""
        SELECT i.id FROM cards_intl i JOIN datas d ON d.id=i.id
        WHERE i.race LIKE '%Rock%'
          AND i.id NOT IN (SELECT id FROM banlist_current)
          AND (d.type & ?) = 0
          AND (d.type & 0x1) != 0""", (EXTRA_MASK,))]
    rock_ids = [c for c in rock if legal_copies(mcon, c) > 0][:40]

    # 池2: 上级召唤教学泛用 —— 恶魔的散步/解放之类? 用经典岩石+守备+祭品相关
    staple_names = [
        'Stumbling', 'Waboku', 'Negate Attack', 'Messenger of Peace',
        'Hinotama', 'Tribute to The Doomed', 'Fissure', 'Riryoku',
        'Justi-Break', 'Stop Defense']
    ph = ",".join("?" * len(staple_names))
    staples = [r[0] for r in mcon.execute(
        f"SELECT id FROM cards_intl WHERE name_en IN ({ph})", staple_names)]
    staples = [c for c in staples if legal_copies(mcon, c) > 0]
    mcon.close()

    con = campaign_con()
    n1 = register_pool(con, "ch2_pool_rock", "第二章·石之守卫", 2,
                       "门卫巨石的领域。岩石族怪兽, 以上级(5星+)守备巨兽为主角, 祭品召唤教学主池。",
                       2, rock_ids, "上级怪兽为主, 教祭品召唤")
    n2 = register_pool(con, "ch2_pool_staple", "第二章·石门赠礼", 2,
                       "守备与持久战通用魔陷, 教'站着挨打'的艺术。", 2, staples)
    flags = {"awakening_25": None, "ch2_cleared": None,
             "black_robe_hint": None, "xiao_suspect_1": None}
    for f in flags:
        con.execute("INSERT OR IGNORE INTO plot_flags VALUES (?,NULL,NULL)", (f,))
    con.commit()

    # 报告: 上级怪兽占比
    mcon = sqlite3.connect(MASTER)
    hi = sum(1 for c in rock_ids
             if (mcon.execute("SELECT level FROM cards_intl WHERE id=?", (c,)).fetchone() or [None])[0]
             and mcon.execute("SELECT level FROM cards_intl WHERE id=?", (c,)).fetchone()[0] >= 5)
    mcon.close()
    print(f"[卡池] ch2_pool_rock={n1}张(其中5星+ {hi}张) ch2_pool_staple={n2}张 flags={len(flags)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
