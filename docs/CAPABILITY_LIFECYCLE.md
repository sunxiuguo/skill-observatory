# 工作流固化与复用

本地系统覆盖设置中的授权目录，部署实例保持整个 privatecode。全局规则决定何时发现/固化，Skill Evolution 决定最小 owner，Creator 编写包，Capability Packs 管理范围，Observatory 保存事实。Stop hooks 只采集，不启动模型、不推断成功、不执行回放。

## 用户任务与信息路径

开工 → 按原 cwd 查询相关能力 → 查目的、来源、权限、当前版本 → 读取 Skill 或调用脚本 → 写调用收据 → 验收结果。阶段收尾 → 判断是否可复用 → existing/script/skill/no_change/hold → 冻结候选 → 正反例验证 → 安装 → 后续任务验证。

后台首屏：能力、待处理固化、调用数量和证据缺口摘要。主要路径：能力目录 → 来源与版本 → 项目/会话/场景调用历史；固化队列 → 决策理由与验证；运行和原有演进/环境页面保留。表格搜索、相关筛选、分页；细节抽屉保留上下文，浏览器刷新保持语言和草稿。

## 本地 CLI 合同

`skillobs --state STATE discover --cwd ORIGINAL_CWD --query TASK` 返回相关且作用域允许的少量能力。`capability-register PATH --owner OWNER --scope SCOPE` 注册既有包，只登记 first_seen；历史出生信息为空，不伪造来源。

`artifact-import FILE` 仅导入脱敏小型验收证据。`capture --spec FILE --auto` 接收 creator 的最小成功收据：name/owner/purpose/background/successful/reusable/source_path/origin；origin 必须有 session_id、turn_id、project、scenario 和有效 evidence_sha256。先检索同名 canonical owner；重复收据幂等，冲突拒绝。证据存在不自动证明作者判断正确，根负责对真实完成验收。

脚本包 `command.json`：entrypoint（包内 Python）、inputs、result、permissions、positive（input/expected 列表）、negative（input 列表），可选 timeout_seconds。当前无人值守执行轨道是可信 owner 编写的 pure_json，无依赖、无外部/文件副作用；使用隔离解释器与临时 cwd、限制数据大小和等待，AST 检查只作辅助，不宣称安全沙箱。其他副作用脚本留给原 owner 的授权/恢复流程，不能因固化获得额外权限。

`capture-validate ID` 冻结文件哈希并验证正例/反例；`capture-activate ID` 对已通过候选安装到私有、动态发现的目录。判断型 Skill 的结构验证不能代替独立向前执行验收；待补证据时保留 HOLD，原有签名演进/结果门不降低。

`replay CAPABILITY_ID --input JSON_FILE --cwd CWD --session-id SESSION --turn-id TURN --scenario SCENARIO --invocation-id ID` 每次检查范围、版本漂移、解释器环境；记录 intent、独立 attempt 和终态，不重试。scenario 以 canary: 开头时明确标注 activation_canary。结果保持 unverified，随后根通过 `usage-import` 关联真实验收 evidence。读 Skill 时同样可通过 usage-import 记录 selected/verified_read/declared_applied；不得把读取变成遵循证明。

账本保存不可变包快照、版本、目的、背景、来源、逻辑 invocation、观察渠道和 attempt。mentioned/selected/verified_read/declared_applied/executed/accepted 按各阶段独立计数，不能相加；任务验收不能推断能力的因果收益。来源缺失保持 UNKNOWN，观察账本不是所有自然调用的完整分母。

## 设计参考和取舍

Product Hunt 用于发现 Latitude、Laminar、Raindrop、Okareo；回查 GitHub 一手说明：Laminar 的 traces/evals/dashboards 分离，Langfuse 的 session/trace 与版本管理。借鉴对象→明细→证据的路径，未复制项目代码。Laminar 声明 Apache-2.0；Langfuse 须按具体文件许可，未引入其实现。

shadcn Data Table 官方指南强调每个表格独立的筛选/排序/分页语义，Radix Dialog 规范强调 inert、焦点约束、Esc 和可访问标题。使用现有 React/lucide 与本地控件实现，避免引入大型仪表盘依赖。来源仅为流程参考，不代表代表性用户可用性或商业证据。

- https://github.com/lmnr-ai/lmnr
- https://github.com/langfuse/langfuse
- https://ui.shadcn.com/docs/components/data-table
- https://www.radix-ui.com/primitives/docs/components/dialog

## 体验审查问题与验收

P1：空队列占首屏，无法找到新增能力 → 紧凑摘要与能力主路径。P1：来源/版本/复用语义缺失 → 结构化谱系与阶段计数。P1：所有页面套 run 状态筛选 → 对象相应筛选与可恢复的空态。P2：表格无限增长 → 分页、稳定顺序、详情导航。实际浏览器验证中英、列表/详情/回退/刷新、窄屏、键盘焦点与离线错误；自动测试不是人类视觉验收。

## 判断型 Skill 的启用与维护

Creator 在不同实际会话里执行冻结 Skill 的向前正例与反例，根核验输入和真实产物后用 `capture-forward ID --receipt FILE` 做受限本地 ingress。receipt 包含 package_sha256、reviewed_by_root（创建来源根会话）、owner、trusted_source=user-owned、授权 scope、permissions、positive/negative 的实际 session_id/turn_id/status=passed 和 input_sha256/result_sha256。原始任务/产物保留私有 evidence，不写入 Skill 包。该入口只检查绑定，不能判定模型文字是否真实；根负责验收。

通过后 `capture-activate ID` 安装到原 ledger 的 canonical 私有目录，按 privatecode-default 延迟读取，不增加全局 Skill 元数据。创建新能力的功能门与既有版本性能晋升的签名 final 门不同，后者仍由旧 pipeline 执行。`capability-retire ID --reason ...` 停止将来复用，保留来源、历史版本与所有调用；修改现有包用原 owner，显式同一个 capability ID 保持谱系，版本漂移不会静默回放。

更新既有包时，Creator 明确提供 `update_capability_id`，必须同 owner、同 scope，重新冻结并验证新版本，沿用 capability ID 和原始出生/来源。新版本分别记录本次 origin 与 capture。不会默默继承旧版本的启用资格，也不会在每个项目复制实现。安装先完成私有临时包并核验，再原子移入 canonical 目录；历史版本与快照保留。

历史维护补录用 `existing_capability_id` + `existing_version_id` 精确关联已冻结版本，不改当前版本、原始出生、版本快照或调用次数。显式 `historical_backfill: true` 是元数据补录：必须同 owner、绑定已存在的能力/版本、沿用原 scope，不能搭配 auto/update 或创建新包。来源可保留当时真实临时工作目录；这不开放该目录的观测、发现、执行或安装。原验收证据和缺口保留在关联 artifact，收据创建时间是补录时间。
