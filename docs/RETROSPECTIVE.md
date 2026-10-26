# 选定会话复盘

手动复盘与每日审查复用 `proactive.py`、私有账本和根收据。选择会话只建立待审工作单，不调用模型、不读取全文、不安装 Skill，也不证明改善。公共安装由当前根执行相同流程；作者的全局 Skill 和 Provider 配置均为可选集成。

## 选择与完成

```sh
skillobs --state PRIVATE_STATE retro-plan --index-db CODEX_INDEX
skillobs --state PRIVATE_STATE retro-plan --index-db CODEX_INDEX --session-id SELECTED_SESSION
```

默认会话来自 `CODEX_THREAD_ID`，缺失时要求显式选择。索引只读精确查询该会话的身份、路径、cwd 和更新时间；观测与诊断作用域都必须匹配。已有归档定位、源格式验证、缺文件与未知版本边界继续有效。返回的是来源指针，根仍须在授权本地读取实际任务、工具结果及产物。

手动批次与每日 `active` 批次使用相同类型的账本记录和完成协议，分别保留槽位；手动选择不推进历史扫描游标，不覆盖每日 pending 工作。重复选择续接 pending，源变化在完成时降为 follow_up；其间已有其他根提交更新审阅时，旧手动收据拒绝覆盖，重新选择并检查最新结果。

若选定会话已经位于每日 pending 批次，返回该批次的选中项及 `total_batch_items`，完成收据只消费这一项，其他项继续 pending。当前来源与冻结计划有差异时，返回 `source_changed_since_plan`；重新读取当前事实，沿源漂移与复查门处理，不把单项复盘当成整批已审。

pending 清单保留冻结义务，不重新读取来源。提交任何 chat 收据时都回查当前观测 scope；撤销后拒绝并回滚整份收据。选定项还需当前诊断 scope，普通每日项继续允许授权范围内的元数据记账。

每日新计划跳过由 pending 手动批次持有的会话，并返回 `selected_pending_skipped`。历史重复工作单若已有较新审阅，旧收据继续拒绝覆盖；根检查最新审阅后，可在旧工作单的原 fingerprint 下明确采用最新 `evidence_sha256` 与 disposition。账本保存 `superseded_reviews` 指针及来源变化，原审阅、owner、证据和后续期限不重写。这只完成旧批次的记账，不把 follow_up/HOLD 改成修复或收益。

根按当前 [审查流程](PROACTIVE_REVIEW.md) 和可用的经验 owner 进行复盘。证据在私有目录保留来源 session/turn、实际观察、最小 owner、原行为→拟改→原因→预期效果、验证和剩余缺口。通过 `artifact-import` 导入紧凑证据，再用现有 `proactive-finish --batch-id BATCH_ID --receipt PRIVATE_RECEIPT` 完成；收据格式、未来复查时间、冲突和源漂移检查保持相同。

## 环境诊断与根因

`review.schema.json` 的可选 `environment_aspect` 与既有根因 `category` 独立：

| 值 | 检查对象 |
| --- | --- |
| navigation | 已存在的信息、入口指针与隐藏依赖 |
| automated_checks | 实际检查命令及其 CI/开发执行接线 |
| coding_standards | 可机器判定的约束与需要上下文判断的标准 |
| steering | 共享入口与条件性指导的归属 |
| tool_economy | 工具调用、返回信息与完整交付成本 |
| no_op_instructions | 指令保留、删除或合并后的可观察行为 |
| information_access | 导航、未捕获事实与权限边界 |

诊断只基于已观察事实，缺少仓库检查配置时不能推断“没有 CI”。固定模式优先由现有确定性检查拦截；指令删除须有行为比较和相关拒绝反例，低频权限/恢复规则保留其触发验证。复盘候选、工程修复、独立 Skill 改善和自然任务收益分别验收。

这些诊断视角参考 Matt Pocock 的 MIT 许可 [retro 固定源码](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/retro/SKILL.md)。会话权限、评测、安装和后续验证沿用本项目与原 owner 的合同。
