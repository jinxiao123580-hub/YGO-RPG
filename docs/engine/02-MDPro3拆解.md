# MDPro3 客户端拆解（本地安装版本实测）

> 实测对象: `E:\FUN\YGO-RPG\YGO\MDPro3`（Unity IL2CPP 桌面版）

## 一、它是什么

MDPro3 = **ygopro 生态的 Master Duel 风格客户端**：Unity 前端 + C# 决斗核心（`Assembly-CSharp.dll` 内嵌 YGOSharp 系实现）+ 内置 WindBot AI + 自定义服务器接入 + 中文全卡库。**它是自带 AI 单机的完整客户端**，不是只能联机的壳。

## 二、目录要点（与本项目相关的部分）

| 路径 | 内容 | 对本项目的价值 |
|---|---|---|
| `Data/hosts.conf` | 服务器列表: `名称 主机 端口 房名后缀`，首行即 `本地7911 127.0.0.1 7911` | ⭐ **自定义服务器确认可行**——加一行即可连自建 SRVPro |
| `Data/hosts2.conf` | 第二服务器列表（233服/Evolution/Koishi 等） | 同上，切换分组用 |
| `Data/locales/zh-CN/cards.cdb` | **中文全卡库** 14505 张（ygopro 标准 datas+texts schema） | 已复制到 `YGO-DATA/db/cards_zh.cdb` 作为母库 |
| `Data/pack/pack.db` | 卡包掉落表: `id, pack_id, pack, rarity, date` 13902 条 | 卡池/掉落设计的发行侧参考 |
| `Data/lflist.conf` | 禁限卡表，多分区（OCG/TCG/MD 按日期） | 自定义「战役禁限表」的格式样板 |
| `Data/script.zip` | **13226 个 Lua 卡片脚本** | 自定义剧情卡可直接增补 |
| `Data/cards_Lite.json` | `cid → passcode` 映射（快速加载用） | 自定义卡需同步维护 |
| `Data/Windbot/Decks/*.ydk` | 内置 AI 卡组（AI_BlueEyes、AI_DarkMagician…） | NPC 卡组可直接放这里被 bot.conf 引用 |
| `Data/Windbot/Dialogs/*` | 性格对话包（Cirno/Ecclesia/Ghoul，多语言 JSON） | ⭐ NPC 人格台词的现成机制 |
| `Data/locales/zh-CN/bot.conf` | **AI 分级配置**: `!名字 / 命令 / 描述 / flags` | ⭐ 见下节 |
| `Picture/Art/{passcode}.jpg` | 卡图 | 展示层素材（注意版权，不分发） |
| `MDPro3_Data/…` | Unity 资产（IL2CPP） | 不动 |

## 三、bot.conf —— 现成的「放水」体系

```ini
!随机-非常简单
Random=AI_LV1
主要是一些沙包。
SUPPORT_MASTER_RULE_2020

!随机-狂野
Random=AI_WILD
普通的人机的卡组会符合其使用的卡池对应的环境的禁限卡表，
但狂野模式的人机的卡组一般不符合任何禁限卡表。
```

每条目=一个可选 NPC：名字、难度命令（`Random=AI_LV2` 或 `DeckFile=xxx.ydk`）、简介文案。**跑团 NPC 可以直接注册成 bot.conf 条目**——章节 BOSS 用专属 .ydk + 指定 Dialog 性格包，杂兵用 LV1/LV2。难度曲线 UP 主手工做的事，这里原生支持。

## 四、与跑团 RPG 的三种集成形态

| 形态 | 做法 | 超规则能力 | 工程量 |
|---|---|---|---|
| **A. 本地 AI 对局** | 玩家在 MDPro3 里直接打 bot.conf 注册的剧情 NPC（本地房），GM 是另一个 LLM 窗口/界面同步叙事 | 只到 L2（自定义卡/房参数） | 最低，**现在就能玩** |
| **B. 自建服务器** | SRVPro(Docker) + hosts.conf 加一行指向它；GM 程序通过房间 API 开房、注入 NPC(bot)、收对局事件 | 到 L3（流程干预/事件流） | 中 |
| **C. fork 客户端/服务端** | 改 SRVPro 或客户端代码，决斗中途注入剧情事件（黑暗决斗演出等） | L4 全开 | 高，不推荐起步 |

## 五、风险与注意

- MDPro3 更新会**覆盖 Data 目录**（其更新机制为整包覆盖），自定义内容（bot.conf/Dialogs/自定义卡）要做好**增量重打**脚本，别手改原文件后指望持久。
- `cards_Lite.json`/`strings.conf`/`script.zip` 三者与自定义卡需保持一致，缺脚本=卡发动无效果。
- 保持非商业、不分发资源包；自定义内容以「补丁包」形式本地使用。
