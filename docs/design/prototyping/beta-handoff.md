# Beta 推免工作区设计交接

联调日期为 2026 年 11 月 28 日。桌面稿与联调补充集中在 [Figma Page 3 交付区](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-506)。[Issue #72](https://github.com/LotteryCamp/OfferPilot/issues/72) 定义设计验收，[Issue #76](https://github.com/LotteryCamp/OfferPilot/issues/76) 对应 Vue 页面重排和接口联调。页面中的院校、日期和数量用于展示布局。联调时以实际通知、当前适用快照和接口读回的状态为准。

## 联调页面索引

| 页面 | 首屏信息与主操作 | 前端入口 | 设计稿 |
| --- | --- | --- | --- |
| 事项工作台 | 当前事项和下一步；有进行中事项时主操作为「进入工作区」；空工作台提供「新建工作区」 | `MattersList.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-507) |
| 事项概览 | 适用范围、当前缺口、来源／候选／任务摘要；「进入来源与条件」 | `MatterOverview.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-597) |
| 来源与自查 | 事项、当前快照、缺口和下一步；缺排名时显示「补充本人排名」，原文和快照紧邻证据 | `SourceConditionsPage.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-758) · [窄屏](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-355) · [已重查](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-627) |
| 排名补录 | 排名、总人数、计算预览及本人确认；允许重跑时显示「保存并重新自查」 | `RankingSupplement.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-869) · [窄屏](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-380) |
| 候选审阅 | 版本、适用范围、决定影响和阻断项；核对条目和来源后在「你的决定」提交 | `PlanReviewPage.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-1117) · [窄屏](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-403) · [已过期](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-651) · [已拒绝](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-642) |
| 阶段与任务 | 确认结果、正式任务与状态；单项展示期限、依赖和依据入口 | `MatterTasksPage.vue` | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-1363) · [窄屏](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-426) |
| 登录 | 表单、失败或会话失效提示；「登录」 | 登录接入入口 | [登录稿](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-456) |
| 材料草拟 | 草稿与引用事实并列；显示待确认事实、补充入口与草稿审阅入口 | 材料草拟设计交接 | [桌面](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-1518) · [草稿](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=16-1629) |

[前端标注与窄屏规则](https://www.figma.com/design/feczCbKUHrybftac7eB7qW/OfferPilot?node-id=27-336)覆盖来源、自查、候选和任务。桌面原型可从工作台进入事项概览，依次查看来源、补录排名、重新自查和决定结果。确认进入正式任务，拒绝进入已拒绝画面。窄屏和登录画板供布局与状态对照。

## 页面层级与组件规范

- 页面按「标题及适用范围 → 当前状态 → 主操作 → 内容与依据」组织。来源母卡展示出处与快照，要求条目展示结论及缺口，任务条目展示可执行事项。三者使用各自的标题和字段顺序。
- 单个决策区保留一项填充主按钮，查看原文、拒绝和返回使用次要按钮或文字链接。按钮触达高度按 44 px 设计。复选框总在决定按钮之前，禁用原因贴近操作；成功后由结果和后续入口接替决定区。
- 视觉沿用原稿的 Noto Sans SC、深紫 `#30266E`、深墨色 `#25243D` 和浅紫 `#F0EDF9`。正文 14 px、辅助说明 12–13 px、区块标题 19 px、页标题 28 px。桌面内容区内边距 28 px，窄屏为 16 px；内容卡圆角 14 px，卡内 18 px。浅紫、琥珀、绿色和红色提示均带可读状态文字。
- ≤1100 px 将来源、候选主辅栏改为单列，来源页依次保留缺口与主操作、自查条目、当前来源；候选页依次展示影响、条目及证据、决定区。条目的原文入口留在条目内，确认阻断提示与按钮同区。
- ≤700 px 排名字段与决定操作纵向排列，标题、说明与出处允许换行。390 px 参考稿采用紧凑导航；各表单、责任性质和期限可单列阅读，主要操作随正文滚动。长标题、链接与机构名须实测无横向滚动。
- 11 月 28 日联调覆盖来源、自查、候选和任务的主流程。材料草拟交接覆盖清单、草稿和事实依据。

## 11 月 28 日实现走查

| 检查 | 通过条件 |
| --- | --- |
| 桌面首屏 | 来源页一眼可见当前快照、首要缺口和补录入口；候选页一眼可见版本、决定影响和决定区入口。 |
| 来源与排名 | 补录并确认本人排名后保存。公开资料的模型传输同意有效时可重查当前来源；缺少有效同意时保留排名，提示授权后重试。证据不足继续显示「待核对」。 |
| 候选到任务 | 确认后读回正式任务与依据；拒绝后核对已有任务数量与状态；刷新后能读回同一决定。 |
| 窄屏与留白 | 在 1100 px、700 px 与 390 px 对照画板，检查主辅栏折叠、动作顺序、长文本换行、重复卡片和无内容的留白。 |
| 异常与恢复 | 按状态说明验证加载、失败、空列表、会话失效、结果待核对和候选过期，记录可复现的实现差异。 |

状态触发、反馈和恢复动作见 [关键状态说明](beta-page-states.md)。实际联调结论应以当次页面与接口证据记录。
