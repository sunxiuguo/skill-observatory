# Web 局部合同

先遵守 [根入口](../AGENTS.md) 和 [项目合同](../docs/PROJECT_CONTRACT.md)，本文件只补充 Web 行为。当前产品使用 React/Vite 与本地 FastAPI；原型/Sites 文件仅保留其原用途，不能把它们的存在视为部署授权或当前构建合同。

- 在 `src/` 接续已选方案 3 与后来接受的白/青界面。参考图决定视觉方向；权限、状态、统计和 HOLD 恢复必须服从实际 API/证据。持久设计决定归项目合同，运行证据归 STATUS/私有收据。
- 默认 zh-CN，完整中英即时切换；路由、搜索/筛选、详情、设置草稿与偏好在切换和刷新后保留。机器 ID/hash/reason code 不翻译。UNKNOWN 不显示成 0，阶段计数不求和，canary 不标成自然收益。
- 改可见路径时按可用的 `product-experience-lifecycle` 接续冻结设计，自己运行实际预览并检查受影响任务、空态/错误/恢复、键盘/焦点、长内容与宽中窄屏。服务与浏览器证据绑定实际构建/state/locale。
- 实际命令为 `npm run build` 与 `npm test`，构建输出 `dist/client/index.html`；分发走根 `scripts/build.py` 复制到 package static。测试会写设置，从仓库根运行 `uv run python scripts/test_web.py`，由同一入口准备隔离 state、实际 loopback API 和 lifecycle fixture，并传入 `SKILLOBS_TEST_ORIGIN`；不能默认写用户的运行服务。
- 不为纯文档/治理变更重新设计 UI；不把 DOM/构建通过当真人体验验收。没有改可见行为时复用有效验证，不重复整套浏览器流程。
