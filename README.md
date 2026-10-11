# YGO-DATA —— 游戏王跑团 RPG 资料库

为「AI-GM 游戏王跑团」（B站《牛戏王》式剧情化教学战役）提供数据与设计文档。
姊妹项目: `E:\FUN\YGO-RPG`（战役运行时 / MDPro3 客户端所在）。

## 目录

```
db/
  ygo_master.db      ★ 主数据库 (只读母本, 构建脚本可随时重建)
  cards_zh.cdb       MDPro3 中文卡库原件备份 (datas+texts, 14505张)
  pack_reference.db  MDPro3 卡包掉落表备份 (日文, 13902条)
  ygo_campaign.db    战役运行时库 (卡池/收藏/抽卡日志/剧情flag)
  starter_demo.ydk   demo 导出的示例卡组 (可直接导入 MDPro3)
sources/
  ygohost_en_rulebook.pdf   官方规则书 v10 (31页)
  lflist.conf / strings_zh.conf / bot.conf   MDPro3 配置样板
  raw/               YGOPRODECK 原始 JSON (cardinfo 24.9MB / cardsets / archetypes)
content/
  bot_campaign.conf  ★ 战役 NPC 条目 (追加到 MDPro3 bot.conf 即可部署)
  dialogs/*.zh-CN.json   ★ NPC 台词包 (复制到 MDPro3/Windbot/Dialogs/)
  decks/npc_*.ydk        NPC 卡组 (店主/门卫/晓, 禁限表合规已校验)
  decks/player_starter.ydk  玩家初始卡组 (40张, 含沉睡青眼白龙)
scripts/
  build_master_db.py 合成主数据库 (五路数据源 -> ygo_master.db)
  pool_draw.py       ★ 情节卡池 + 加权抽卡 + .ydk 导出
  build_ch1_content.py  第一章内容生成 (卡池正式化 + NPC/玩家卡组 + 校验)
docs/
  engine/01-资料调研报告.md   官方+第三方生态调研结论
  engine/02-MDPro3拆解.md     客户端目录/机制/集成形态
  design/01-情节卡池机制.md   ★ 由剧情决定卡池
  design/02-随机抽卡机制.md   ★ 保底/权重/剧情接口
  design/03-剧情超规则.md     ★ L0-L4 分级超规则体系
  campaign/00-战役总纲.md     ★ 八章结构/规则解锁/难度曲线 (改编牛戏王+决斗者王国)
  campaign/01-第一章剧本.md   ★ 分镜稿含教学台词模板与胜负分支
  campaign/02-跑团规则.md     2d6 检定/羁绊/败北分支表/觉醒度
  campaign/03-GM提示词.md     ★ AI-GM 系统提示词(十条纪律)+使用流程
  campaign/04-存档结构.md     存档 JSON schema
```

## 快速上手

```bash
cd scripts
python build_master_db.py      # 重建主数据库 (需要 sources/raw 下的 JSON)
python pool_draw.py init       # 初始化战役库
python build_ch1_content.py    # 生成第一章: 正式卡池+NPC卡组+玩家初始卡组
python pool_draw.py draw ch1_pool_dragon+ch1_pool_staple 3   # 抽3包新手包
```

部署第一章到 MDPro3:
1. `content/bot_campaign.conf` 内容追加到 `MDPro3/Data/locales/zh-CN/bot.conf`
2. `content/dialogs/*.json` 复制到 `MDPro3/Data/Windbot/Dialogs/`
3. `content/decks/player_starter.ydk` 导入玩家卡组
4. MDPro3 本地 AI 对战选择"战役-店主磨坊"开打, GM 窗口用 `docs/campaign/03-GM提示词.md`
注意: MDPro3 更新会覆盖 bot.conf, 更新后重新追加（步骤1-2）。

## ygo_master.db 表速查

| 表 | 内容 | 关键字段 |
|---|---|---|
| datas / texts | 中文卡库 (ygopro schema) | id, type/atk/def/level, name, desc |
| cards_intl | 国际库 (按 passcode 对齐) | name_en, archetype, ban_tcg/ocg, md_rarity, tcg_date |
| card_in_sets | TCG 收录 (44605 条) | set_code, set_rarity, set_price |
| card_sets_info | 646 卡包系列 | set_code, tcg_date |
| archetypes | 661 字段 | archetype_name |
| card_packs_jp | 日文收录 (13902) | pack_id, rarity, date |
| banlist_current / banlist_history | 禁限表 (当前/历史) | status(禁止/限制/准限制), list_name |
| card_tags | AI 打标接口 (空) | strategy, teaching_memo, pool_tier |
| meta | 数据源版本 | ygoprodeck_db_version=147.23 (2026-10-08) |

## 数据更新

YGOPRODECK 库约每两周更新: 重跑
`curl 'https://db.ygoprodeck.com/api/v7/cardinfo.php?misc=yes' -o sources/raw/cardinfo_full.json`
+ `python scripts/build_master_db.py`（MDPro3 本体更新后，重新从 Data 目录拷 cdb 即可）。

## 版权

卡片名称/文本/图片 © Konami / STUDIO DICE / 4K Media。本库仅个人非商业使用，不对外分发资源文件；对外产物只引用 passcode。
