# LLM 大脑 —— 让 LLM 控制对手出牌

> 代码: `E:\FUN\YGO-RPG\YGO\windbot-llm`（WindBot fork, 上游 IceYGO/WindBot MIT）
> 架构: 引擎裁定不变, LLM 只做选择题。所有决策点失败即回退脚本, 永不卡死对局。

## 一、原理

WindBot 以客户端身份连接 ygopro 服务器, 内嵌 C# 版 ocgcore 引擎。原版 AI 的决策在 `Game/AI/Executor` 的 30+ 个虚拟方法里; 本 fork 新增:

```
服务器询问决策(合法动作已由引擎枚举)
   → LLMExecutor 覆盖决策点: 局面JSON + 选项列表 + NPC性格提示词 → LLM
   → LLM 返回 {"choice":n} / {"yes":bool} / {"cards":[...]}
   → 校验合法性(索引越界/数量不符→回退) → 引擎执行
   → 服务器RETRY(回答无效) → OnActionFailed() → 连续2次失败后保守应答
```

**关键纪律**: LLM 拿到的选项都是引擎枚举的合法动作——它不能发明卡、不能违反规则, 只能"选择"和"演"。这就是防幻觉的架构保证。

## 二、已覆盖的决策点（LLMExecutor.cs）

| 决策点 | 方法 | 说明 |
|---|---|---|
| 发动/连锁与否 | OnSelectYesNo | 最能体现性格的决策 |
| 效果选项 | OnSelectOption | |
| 选卡(检索/取对象) | OnSelectCard | 校验数量[min,max]与索引 |
| 祭品选择 | OnSelectTribute | |
| 表示形式 | OnSelectPosition | |
| 召唤 or 盖放 | OnSelectMonsterSummonOrSet | |
| 攻击目标(含直击) | OnSelectAttackTarget | 直击不可行时自动回退 |
| 宣言卡名 | OnAnnounceCard | |

暂用脚本（后续版本覆盖）: 战斗阶段整体循环(OnBattle 攻手选择)、放置格(OnSelectPlace)、洗牌排序、猜拳。角色卡专属连招(各 Deck Executor)在 Brain=LLM 时由 DefaultExecutor 基类行为替代。

## 三、局面喂给 LLM 的内容（防作弊约束）

自己: LP/手牌(明牌+名字)/怪兽区(攻防/表示)/魔陷区/墓地顶/卡组数
对手: LP/手牌**数量**(看不到牌面)/怪兽区/魔陷区/墓地顶/卡组数
→ LLM 只知道公开信息+自己手牌, **没有上帝视角**, 放水必须靠"演"而不是作弊。

## 四、构建与运行

```bash
# 依赖: .NET 8 SDK (dotnet build 自动拉取 net48 引用程序集包)
cd E:\FUN\YGO-RPG\YGO\windbot-llm
dotnet build WindBot.csproj -c Release
# 产物: bin\Release\WindBot.exe —— 旁边需要 cards.cdb (用 zh-CN 版即得中文卡名)

# 单机对战启动 (Host 指向服务器):
WindBot.exe Name=店主·磨坊 DeckFile=deck/npc_miller.ydk Dialog=dia_owner.zh-CN ^
  Host=127.0.0.1 Port=7911 ^
  LLMEnabled=True LLMApiKey=sk-xxx LLMModel=gpt-4o-mini ^
  LLMPersona="旧货店店主,爱吹牛,实际是萌新,经常后悔自己的出牌" LLMMercy=2
```

| 参数 | 默认 | 说明 |
|---|---|---|
| LLMEnabled | False | 总开关(关=原版脚本AI) |
| LLMEndpoint | api.openai.com/v1/chat/completions | 任意 OpenAI 兼容端点 |
| LLMApiKey | (空) | Bearer token |
| LLMModel | gpt-4o-mini | |
| LLMPersona | 骄傲的老派决斗者 | 性格+口头禅+演出指导, 注入 system prompt |
| LLMMercy | 0 | **放水等级**: 0全力 1留余地(非斩杀局不致命) 2明显放水(偏好弱选项) |
| LLMTimeout | 12000 | 单次决策超时ms, 超时回退脚本 |

## 五、与跑团战役的对接

- **每章每 NPC 一个启动配置** = bot.conf 条目扩展版: DeckFile(战役卡组) + Dialog(台词包) + LLMPersona(性格) + LLMMercy(难度曲线: 1-2章=2, 3-5章=1, 6-8章=0)
- **GM 层**: MDPro3(玩家) ←→ 自建服务器 ←→ WindBot(LLM大脑)。GM 读对局事件流解说, 抽卡/奖励走 ygo_campaign.db
- **延迟演出**: LLM 决策 1-3 秒/次, 配合 Dialog 台词("让你见识一下……")反而像真人思考

## 六、待办（下一步）

1. 服务器: SRVPro(node+redis) 或轻量 ygopro 中继, Docker 不可用则 node 直跑
2. E2E 测试: WindBot(LLM) vs WindBot(脚本) 在本地服务器互打完整一局
3. MDPro3 hosts.conf 加自建服条目, 玩家客户端接入
4. 覆盖剩余决策点(OnBattle/OnSelectPlace)与 L4 剧情改判钩子
