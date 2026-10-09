# Skill Observatory 项目合同

本合同固定项目要解决的问题、不可降低的验收和职责；[STATUS.md](STATUS.md) 是当前进度与证据的唯一入口。本合同不保存滚动状态；授权来自用户，下面仅记录已明确给出的本项目 Git 交付授权。当前用户可以明确调整目标；必须展示取舍、更新合同和受影响检查，不能静默改标准。

## 第一性原理与最终目标

用户需要后续真实任务更可靠地完成，而不是更多 Skill、更高自评分或一个持续运行的 daemon。必要因果链是：真实执行 → 有身份和覆盖边界的观察 → 正确归因 → 最小 canonical owner 的候选/固化 → 独立验收 → 授权安装 → 新上下文复用 → 后续可比较结果。任何一步缺失都限制对应声明，不能由其他步骤补分。

治理分三层：根 AGENTS 是每次开工入口；本合同定义目标和证据；现有 runtime、领域 evaluator、原安装器及 CI 执行机器可判定的门。自然用户结果仍需要真实样本/真值，文本和结构检查不能保证它。

### O1 真实观测与归因

限定已授权作用域，保留 completed/failed/interrupted/child 的实际身份与独立事件；持久队列、去重、中断恢复、NO_CHANGE/HOLD 均可追溯。仅展示 observed_receipts_only 覆盖，未跟踪的全局分母未知。提及/发现 Skill 不能证明加载或遵循。

### O2 可信改善与安全落地

候选与精确父版本在可比较模型/最高已验证档位、任务和独立环境下配对。冻结 oracle、权限、阈值、数据与预算；开发/选择/最终集隔离，最终集消费后不可反复用于认证。必须有真实领域真值、独立签名、关键回归和全部尝试成本；合成、无增益或缺证据保持 HOLD。

安装须具备匹配 owner/surface 授权，并走原安装器、before/after 哈希、备份、prepared intent、CAS、实际回读和可恢复回滚。未知外部提交先核对，禁止自动重放。不能让 proposer 修改 verifier 或通过 UI 获得新权限。

### O3 后续真实结果

evaluated → installed → activated → live_verified 分别证明；激活需安装后创建的新上下文、实际加载的精确版本和独立任务结果。激活 canary 不等于自然任务收益。收益比较须注明窗口、任务族、模型/环境、独立分母、失败/返工/接管及全部成本，缺失保留 UNKNOWN。

“安装后”以实际写入及回读完成的 `applied_at` 为界；旧记录缺少该字段时保持 `INSTALLATION_APPLY_TIME_REQUIRED`，不能用准备时间伪造迁移。live 验证拒绝缺文件、symlink 或当前哈希漂移；`live_verified_at` 和 `verified_skill_sha256` 只声明该次回读时的历史证据，不保证未来持续不漂移，更不证明统计收益。

### O4 工作流固化与复用

真实成功/失败决定 existing owner、deterministic command、Skill、project_record 或 no_change/HOLD；输入、产物、目的、背景、来源项目/session/turn、权限和冻结版本可追溯。普通 Skill 不复制 runtime。跨项目复用前核对版本/作用域/副作用，逻辑调用与重试分开，读取、遵循、执行、验收阶段不相加。判断型 Skill 的结构通过不能替代独立向前任务测试。

### O5 完整产品体验

延续用户选定的方案 3 与后续接受的白/青界面；默认 zh-CN，完整即时中英切换并持久化，保留路由、筛选、详情和草稿。状态/错误/HOLD 恢复来自真实 API。受影响的任务主路径、空态、离线/重启恢复、键盘焦点、长内容、宽中窄屏在真实浏览器验证；代表性人类体验单独保留证据边界。

### O6 可恢复运行与可分发交付

本地服务安装/启动/停止/升级/卸载可恢复。公共安装在干净源码、无作者私有配置下可运行；许可、显式 source allowlist、源码/分发字节与远端最终提交身份核对。公开代码、CI 和 GitHub 可见性只证明软件交付。Git 交付依下述明确长期授权；其他发布仍须匹配授权，不继承旧实施 prompt。

### O7 方法递归

先证明 Skill 改善，再比较改进方法自身。被接受的 method 必须实际生成下一代候选，有精确 proposer_method_version 谱系、独立下游收益和全探索成本，才可声明递归自改善。固定 oracle、权限与 kernel 不能被被评测方法修改；没有下一代真实证据保持 UNVERIFIED。

## 验收层级与不越级声明

| 层级 | 必要证据 | 不能替代它的结果 |
|---|---|---|
| 工程/循环机制 | 实际 API、持久队列、恢复/拒绝、真实适用工具与运行收据 | 退出 0、健康、模型说完成 |
| Skill 任务改善 | 精确父子比较、独立真实 final truth、回归/权限、全尝试成本 | 合成 fixture、review 分数、一次 canary |
| 后续真实用户效果 | 新版本真实激活后可比较 cohort 的完成/返工/接管/时间等 | 测试、安装成功、评测分数、发布 |
| 方法递归改善 | 已接受 method 生成下一代、独立下游比较及谱系 | 循环重复运行、合成选择器 |

不足不是零，也不是已经达成。工程交付可以验收，但不能将整个项目的最终目标标成完成。拒绝/no-gain 是正确机制结果，不是改善证明。

## 唯一 owner 与按需路由

| Owner | 负责结果 | 仓库入口 |
|---|---|---|
| skill-evolution-loop | 执行经验归因、最小程序 owner 与固化选择 | [CAPABILITY_LIFECYCLE.md](CAPABILITY_LIFECYCLE.md)；`capture.py` |
| recursive-self-improvement | 方法实验/谱系与递归证据 | `pipeline.py`；独立领域评测与结果合同 |
| Observatory | 事件、账本、版本、review、编排、受控 API/CLI/后台 | `runtime.py`、`store.py`、`capabilities.py` |
| 领域 evaluator | 独立任务正确性/质量/标签 | `evaluation.py`、`final_gate.py`、`outcomes.py`；[CONFIGURATION.md](CONFIGURATION.md) |
| 原安装器/能力 owner | 作用域、权限、安装事务、回滚 | `owner_installers.py`、`installations.py` |
| 当前根 | 当前任务目标、架构、授权、冲突与最终验收 | [../AGENTS.md](../AGENTS.md) |

可用的全局 Skill 提供流程，不取代上述仓库实现。领域参考、插件或工具按任务延迟加载；既有 owner 优先。纯规则/后端维护不要求重做市场或视觉设计，体验变更按可用的 `product-experience-lifecycle` 接续冻结方向。

## 迭代与验证合同

非微小任务开工先明确：对应 O1–O7 的目标、当前事实、一个可验收产物、写入 owner、权限/成本边界、通过与拒绝条件。计划可调整，目标与证据标准不静默降级。只读审查不自动变成实施；Git 交付仅采用已给出的独立授权，实施不自动授权其他发布。

2026-10-09 用户确认现有 `sunxiuguo/skill-observatory` 是公开仓库后，明确授权每次任务验收完成自动提交并推送到 `origin/main`。按根 AGENTS 的范围/公共内容检查、快进、并发保护、远端 SHA 与最终提交 CI 回读执行；这是本项目的长期 Git 交付授权，不能从配置或旧 prompt 扩大为任意外部操作。无改动不造空提交，失败保留未同步状态。

每轮至少检查实际 diff 和受影响行为；治理改动运行 `uv run python scripts/check_project_contract.py`。机械检查清单及不可缺的目标/回归映射由 [project-contract.json](project-contract.json) 维护，检查器不执行其中的任意命令或加载候选代码。CI 在完整 pytest 前检查合同，再执行现有真实容器、构建、HTTP API/DOM 与 wheel 安装门。

| 改动 | 必要验证 |
|---|---|
| 文档/入口/治理 | 合同检查、真实案例与拒绝反例、引用/命令存在、实际 diff |
| 事件/归因/账本/版本/固化 | 受影响 pytest；身份、隐私、重复/重启、漂移和拒绝路径 |
| 评测/broker/安装/激活 | 受影响 pytest + `SKILLOBS_REQUIRE_CONTAINER=1 uv run pytest -q`；签名、final 消费、CAS、未知重放、新上下文与回滚 |
| Web | `npm --prefix web run build`；`uv run python scripts/test_web.py` 准备隔离私有 state、专用 fixture 与实际 loopback API，测试后自动停止；受影响真实浏览器路径、中英/刷新/键盘/视口 |
| 分发/依赖/安装 | `uv run python scripts/build.py`（含 archive 审计）；干净源码安装/doctor 与实际受影响命令；公共内容/许可 allowlist |
| 获授权的服务更新/发布 | 原 service 生命周期、实际端口/API/资源版本回读；发布再核对远端最终 hash/visibility/CI |

Web 集成测试会写设置，不使用正在运行的用户 state；它依赖专用 lifecycle fixture，沿用 [README](../README.md) 的测试配方。工程验证复用身份匹配的有效收据，不因治理改动重做 pilot，也不因服务存在就操作它。作者本机地址由 STATUS/当前实际配置核对，公共默认端口不证明本机端口空闲。

收尾说明工程验收与收益证据各自达到了哪层、未完成项/阻塞/最小解阻需求。真实状态变化更新 STATUS；原始日志、备份、运行收据放私有目录，入口不累加复盘。目标、权限、评测标准和 owner 变更需单独审查，删除结构检查或回归来掩盖退化不算优化。

## 治理依据与边界

2026-10-09 核查时 Git 历史没有根 AGENTS.md；目标保存在历史设计/实施 prompt，Web 入口还是与当前脚本不符的原型模板。缺口是持久入口和维护门，不能据此认定已有业务机制不存在。

[OpenAI 官方指令文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 说明从 Git root 到 cwd 加载逐层指令、同层 override 优先及新会话重建。故根入口负责全仓库、Web 入口只补局部合同；检查未分类/覆盖入口、空文件、失效引用和分发遗漏。文件保持简短，不修改全局配置来绕过加载上限。结构检查通过不证明模型遵循、领域效果或收益；有权限的提交者仍可改检查器，授权与独立 review 门继续有效。

旧 ARCHITECTURE/EVALUATION/DELIVERY_PLAN/IMPLEMENTATION_PROMPT 是原设计和原任务背景；接口、版本、进度和当时授权以当前代码、当前任务和 STATUS 回读为准。本机历史验收 `docs/LIFECYCLE_ACCEPTANCE.md` 不作为分发依赖，不能把其“本轮交付完成”推广成 O2/O3/O7 全部完成。
