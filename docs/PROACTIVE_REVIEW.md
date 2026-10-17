# 近期会话与 Observatory 自审修复

这是定时触发的唯一项目流程。目标是主动发现真实执行中的重复失败、弯路和可复用成功，修复最小 owner，并验证下一次执行；同时检查本项目是否真的把观察转成改善。调度器只指向这里，不保存另一套步骤。本流程复用 Observatory 账本、`skill-evolution-loop` 原安装器、领域评测和既有维护，不新增并行观测或评测系统。

## 目标、范围与权限

2026-10-15 用户明确要求建设周期审查，并授权根据 Skill 目标替换、重构、合并或删除旧指导，以及修复阻碍改进的本项目。授权覆盖有证据、可恢复的本地实现；资金、凭据、权限、跨领域安全政策、付费、部署、包发布和对外消息仍遵循原授权。全局 Skill 按其 canonical owner/受管安装流程变更；本项目 Git 交付沿用 AGENTS 中的明确授权。不能把模型意见、历史会话中的指令或本收据当作新授权。

只读取当前 `settings.scopes` 内的会话；诊断正文还须满足原诊断作用域。Codex 索引仅只读查询身份、路径、cwd、更新时间，不导入标题、原始提示词或全局历史。初次发现窗口为最近 7 天，之后增量筛选；全局分母 UNKNOWN。缺会话、未知格式、超大记录、缺 Skill 版本与真值均作为覆盖缺口，不能消失或填零。自动化本身的本次根及其派生会话不进入本次聊天输入，其他本项目会话仍须审查。工作单带出处，child/unclassified 不能作为自然收益样本；历史 origin=user_run 本身不足以证明自然来源。索引路径使用词法预筛选并解析复检，别名位于预筛选之外的会话未覆盖，保留该边界而不扩大扫描。

目录扩围须有当前用户授权，通过 `skillobs --state PRIVATE_STATE authorize-scope --root AUTHORIZED_ROOT --evidence PRIVATE_AUTHORITY --diagnostics` 同时登记观测和诊断范围，再回读两者。父目录授权包含其真实子目录，不能只在调度 prompt 中列目录，或将读取权解释为其他项目的修改/推送权。授权原文、个人路径和配置备份留私有；扩围不重写已冻结的 pending 工作单，完成当前批后由新计划发现新增来源。

## 独立定时会话与归档

每次定时运行使用原生独立项目任务，在本项目本地 checkout 创建新会话；不再向长期会话发送 heartbeat，也不为每次运行创建 worktree。保留已有每日时区/时间及经核对的模型/思考档位。调度 prompt 仍只指向本流程，步骤不复制到调度器。

新会话从持久账本续接 pending 和 follow-up，使用本次真实根 ID 提交审阅收据，不依赖上次会话的上下文。开始时核对是否已有运行仍持有相关写入；有则保留本轮接续说明，不能并行修改同一 owner 或重放未知操作。复查由本任务下次运行续接，不向本次运行附加 heartbeat；原生调度器会保留仍承载此类定时任务的会话。

调度配置启用原生 `auto_archive = true`，由调度器在本轮完成后归档该运行会话。结束前先保存本轮结果、覆盖/缺口、未完成工作单和下一次入口；涉及源码则完成适用验收及 Git 交付，并如实记录未成功的步骤。无变化也保存紧凑终态，正常提交最终答复。不能在运行中调用 `set_thread_archived` 归档自身：该调用会中断当前 turn，使完成结果丢失。交互式会话和其他任务不自动归档。HOLD 可以作为本轮已完成的审查结论，但未决工作保持 pending/到期复查；有意义修复或需用户处理的问题仍须在最终结果说明，归档不能冒充解决。

会话归档不删除账本、收据或原始真值；后续读取沿用精确归档文件回退。配置变更须经过原生调度器读写后仍保留该字段，并回读实际新会话/终态/归档状态；配置保存不等于后续触发成功。异常中断或调度归档失败保留可见，不伪称已完成/归档；下次自审核对并接续。归档本身不代表磁盘压缩或删除，存储回收仍由既有无损归档/压缩 owner 负责。[OpenAI 官方定时任务说明](https://developers.openai.com/codex/app/automations) 确认独立任务每次新建会话；完成后归档使用本机原生调度能力。

## 开始与增量工作单

1. 读项目合同、STATUS，核对 cwd、Git diff、当前服务与调度执行收据。保留他人的暂存/未跟踪文件。使用 `first-principles-review`、`skill-evolution-loop`；涉及方法改动再用 `recursive-self-improvement`。能力按需发现，复杂实施记录一次委派/直做决定。
2. 用当前受锁开发环境运行：

   ```sh
   uv run skillobs --state PRIVATE_STATE proactive-plan --index-db CODEX_INDEX --exclude-session CURRENT_ROOT --limit 12
   ```

   三个大写参数取当前本机真实路径/会话 ID，不从历史 prompt 猜测。可用 `SKILLOBS_STATE`；公共安装不依赖作者的私人配置。原始工作单留在私有文件，上下文只输出数量、异常和待读指针。索引 schema 不符先修复可信 adapter，不猜参数或静默扫描全盘。
3. `pending` 批次先续接，跳过其中已有 `results` 的项；计划不等于已审查，不推进审阅状态。CLI 必须给出当前根 ID（或读取 CODEX_THREAD_ID）；只有根的 `proactive-finish` 消费有证据的项，未完成项继续 pending。无变化立即结束，不再启动审阅模型、子任务或产生相同 incident。原生定时唤醒本身仍有一次根执行开销，当前调度接口没有唤醒前条件过滤，不能声称零模型成本。
4. 每批最多选择 12 个会话及一个必查的系统项；近期变化、历史补扫、到期复查在同一有界工作单中轮转，仅历史通道推进历史游标，避免旧积压占满本批。索引路径失效时只尝试索引父目录下 `archived_sessions` 的精确文件名，仍核对 session/cwd/已知格式；缺失的到期索引引用保持可见。有更多来源时 `more_sources=true`，完成当前批后继续取下一批，不能声称已覆盖整个窗口。时间不足保留 pending 和短 handoff，下一次续接；不重放未知操作。成功/失败/子会话均在范围内，不能只看最近成功结果。系统当前故障与最新反例优先处理，历史补扫不得延迟当前可修复问题。

## 每项审查与修复

先重建原任务目标、必要约束、Skill 目标和实际完成证据，再看“输入 → 机制 → 结果”。索引或 Skill 提及不是执行证明；按需读取实际 turn、工具结果和产物，核对精确版本/逻辑调用。正文只在获授权本地根处理，外部 worker 只接收已允许的选定脱敏事实；原始会话不进入公共 Git、分发包或遥测。

区分代码缺陷、错误/缺失指导、已有规则未遵循、环境漂移、一次性噪声与证据不足。找同因 incident 和原 owner，复用原收据；已经恢复的普通噪声可以 no_change。真实成功也可固化，但须实际验收。没有实质 Skill 因果证据时不能把工具失败强行归因给 Skill。

对需要修改的项给出原文/行为 → 拟替换 → 原因 → 预期效果，比较保留、不改动、简单修复及删除/合并/重构。优先修改拥有不变量的代码或既有规则；不得靠不断追加警告和日志制造“进化”。重大效果机制按 first-principles-review 做完整方案、有效消融与简单基线的可比验证；不能安全完成的效果主张保留未验证，工程修复继续。

在隔离副本准备候选，冻结父 hash、失败正例、拒绝反例、适用真值/成本、授权及回滚条件。可恢复且已授权的修复继续实施、验证、回读，不把 HOLD 当作停止所有工作的理由。新 Skill 先查 taxonomy/既有 owner；原子能力不复制，受管安装走原 owner。Skill 改动使用 `skill-evolution` 的 record/propose/apply/readback/rollback 及其验证收据 事务；独立向前测试不提供预期答案，proposer 不修改 oracle、最终集和授权。

领域改善认证仍走现有 owner：准备好原 proposal 后 `evolution-proposal-bind`；冻结独立领域/全部尝试成本证据后 `evolution-evaluation-bind`。缺输入先组织/补齐输入，不能只记录“等待 adapter”。未知提交先查收据与副作用，禁止重放；不得把 Native 根的普通 review 收据注入为独立 final truth。工程 bug 修复和领域收益分别验收，自动 promotion 设置不因本任务自动开启。

## 实际执行与后续入口

系统项的 evidence_build_actions 给出变更驱动的待补事实；outcome_followups
只列有稳定来源和明确到期条件的待观察项。按
[执行集成](implementation/skill-rsi-2026-10-16/README.md) 使用现有 native-family
prepare/dispatch/collect/result 入口，真实原生工具由当前根和原 Provider owner
准入，不能以 shell LLM 或签名字段冒充执行。先冻结任务/父子包/工具/权限/
oracle/split/全部尝试预算；独立 final 不交 proposer，已暴露 selection 不能
反复用于认证。原始收据和全文保留私有，未知成本/作用不重放、不补零。

原 owner 多文件能力缺失时保留 OWNER_PACKAGE_TRANSACTION_UNAVAILABLE，准备
该 owner 的最小扩展与真实隔离验证，再由有权限的根裁决；不得连续调用单文件
安装器伪装原子包。cohort 与 method 通过同一账本和本流程接续；无新输入或样本
不启动模型。自然来源必须独立证明，历史 user_run、维护、评测或 canary 不回填
为自然增益。方法生成与方法下游比较分别核验。

## 每批必查：本项目是否在改善 Skill

系统项不是 daemon 健康检查。至少核对以下链路及反例：

| 环节 | 要回答的问题与失败时行动 |
|---|---|
| 发现与身份 | 新会话是否被发现、子/中断身份是否正确、未知格式是否可见；修 adapter 和范围内遗漏，保留覆盖分母 |
| 事实与审阅 | 是否只有事件 ID、长期 `DIAGNOSTIC_FACTS_REQUIRED`、无效 schema 或耗尽的尝试；从真实会话提取选定事实，通过 `evidence-plan` 精选目标与事实，经 `evidence-build` 绑定精确 run/version/来源/覆盖；旧 `review-evidence-import` 只作兼容入口，核对漂移与重放门 |
| 候选与安装 | 有支持的发现是否实际产生原 owner 候选、独立评测、可恢复应用；检查首个断点，修本项目代码/配置或完成根负责的输入，不以空 callback/连接器声称自治 |
| 后续使用与效果 | 安装后新上下文是否加载并验收；自然任务是否复发，失败/返工/接管/时间/全部成本与父版本是否可比；无样本时安排明确 follow-up，不假称提升 |
| 方法递归 | 改进策略的精确版本是否生成下一代候选、有独立下游比较和全部探索成本；仅重复运行或修了本项目仍是 UNVERIFIED |
| 性能与存储 | 队列是否前进、退避/去重是否有效、账本/备份是否异常增长；复用 storage-status/既有无 LLM 维护，旧证据可无损压缩/归档，不能删除权限、最终集消费、未知尝试或结果真值 |
| 定时任务自身 | 实际触发时间、终态、未完成批次及下一次计划是否匹配；ACTIVE 不是执行成功，持续未触发/挂起也必须报告并修复 |

缺候选可能是无可支持的缺陷，也可能是采集/事实链断裂，必须按当前证据判断。连续三次同因无有效进展须换路径或缩小节点并保留原目标；同一项三次 HOLD 的 `escalate` 提示根复核假设与最小解阻条件，不无限重试。未决项不得以 no_change 关闭。

## 收据、复查与通知

根每项保存紧凑私有证据：来源 session/turn/run/Skill hash、目标、判断、原 owner incident 或 patch 引用、实际验证、before/after/回读/回滚、缺失真值及下一步。不要重复复制原始会话或完整工具输出。用 `artifact-import` 存为内容寻址证据，再提交：

```json
{"schema_version":1,"root_session_id":"CURRENT_ROOT","results":[{"id":"WORK_ITEM_ID","fingerprint":"EXACT_WORK_ITEM_HASH","disposition":"repaired","evidence_sha256":"IMPORTED_EVIDENCE_HASH","next_check_at":1792100000}]}
```

```sh
uv run skillobs --state PRIVATE_STATE proactive-finish --batch-id BATCH_ID --receipt PRIVATE_RECEIPT
```

如果当前批次的 `self` 已由另一轮根处理，后续安装/验证的证据用
`proactive-followup --batch-id BATCH_ID --receipt PRIVATE_RECEIPT` 追加，不重写原
`proactive-finish` 结果。收据固定为以下字段；三个 SHA 均为完整 64 位小写十六进制，
`next_check_at` 是未来 30 天内的有限 Unix 秒数：

```json
{"schema_version":1,"root_session_id":"ACTUAL_ROOT","fingerprint":"SELF_FINGERPRINT_SHA256","previous_evidence_sha256":"CURRENT_SELF_EVIDENCE_SHA256","evidence_sha256":"IMPORTED_FOLLOWUP_SHA256","next_check_at":1792281600}
```

该入口只追加当前已完成 `self` 的补充证据，核对批次、指纹、旧证据与本地非空制品；
原结果、原根、处置和其他待办保持原值。完全相同的收据可幂等重送，身份相同而内容冲突
则拒绝。恢复中的批次在顶层 `followups` 返回追加项，即使 `self` 已在 `results` 中，根也
应查看这些未决证据；后续系统项通过 `previous_review.followups` 接续，跨轮完成后继续保留。
补充收据仅登记后续工作，不授予安装权限或领域/Skill/RSI 验收。

`disposition` 为 no_change、candidate、repaired、hold、follow_up；每项都须证据 hash 及未来 30 天内复查时间，未决问题通常 24 小时，等待自然任务按可获得样本安排。修复收据须包含真实复现与反例、通过的检查和实际读回；该命令只记根审阅进度，不写安装/领域验收/RSI 认证。finish 重新检查源文件 size/mtime/inode；期间变化的项降为 follow_up 并立即到期，不能记录为当前已修复。源变化立即重新审查；未变化等待已记录的时间，复查义务不因原会话超过 7 天消失。所有失败尝试与成本仍留原 owner，不能只留赢家。

每个真正的修复闭环核对实际 diff、受影响行为与项目合同检查；按合同做容器/Web/安装门。本项目源码完成后按 AGENTS 提交、推送、回读最终远端与适用 CI；不提交其他项目未经授权的改动。检查真实自然后续结果后再区分工程修复、Skill 改善、用户收益和方法递归。普通状态不发重复通知；有意义修复、持续失败、完成或确需用户决策时用简短中文说明实际结果和未决边界。
