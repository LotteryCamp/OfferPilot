# OfferPilot Beta 验收追踪与发布记录

| 项目 | 内容 |
| --- | --- |
| 团队与负责人 | 鹦伟达 · 魏之皓（PM） |
| 冲刺周期 | 2026 年 11 月 25 日至 12 月 3 日，以下日期均为北京时间（UTC+8） |
| 跟踪入口 | [Beta 里程碑](https://github.com/LotteryCamp/OfferPilot/milestone/2) · [范围与发布 #71](https://github.com/LotteryCamp/OfferPilot/issues/71) · [测试与验收 #78](https://github.com/LotteryCamp/OfferPilot/issues/78) |
| 仓库核对基线 | 2026 年 11 月 26 日（北京时间）核对 [main @ 722c367](https://github.com/LotteryCamp/OfferPilot/commit/722c3679c59c1a42b43d05f190fe17dd9bda8d5e) |
| 当前交付 | 本次提交建立验收基线；候选版本和发布结论待实际验收后填写 |

## 1. 交付范围

**P0（本轮必验）**为推免个人工作区。用户注册或登录后，在本人工作区创建事项，读取公开通知，查看要求、适用范围、出处及缺口，补录排名并重新自查，审阅候选计划，确认后生成个人任务。退出、重登或刷新后，状态应可正确恢复。账户隔离、来源与模型错误处理、核心页面层级和可复现启动均随主流程验收。

推免自查可给出初步判断、说明缺口并提示用户核对。判断以适用的公开官方原文和本人确认的事实为依据。个人截图、沟通记录等作为当前事项的参考线索。联系导师的先后和必要性按通知或具体阶段判断。缺少明确依据时显示待核对。用户自己确认所提供事实和材料的可用性，工作区保持本人可见，候选计划、材料草稿和私有文件由本人审阅与处置。

**P1（扩展）**包括一个公开竞赛通知模板，以及个人材料草拟、编辑和 DOCX 导出。前期可准备规则样例、设计和接口。11 月 29 日检查推免闭环，若仍有核心阻塞，11 月 30 日起暂停 P1 集成，集中修复 P0。P1 逐项按实际验收结果纳入交付，竞赛的展示范围限于选定样例。

当前模型传输同意契约覆盖公开资料分析，不包含个人事实、个人材料或用户导入件。若材料草拟需要将个人事实发送给外部模型，集成前先补充相应披露和授权契约，至少绑定用途、所选事实及其版本。用户明确同意后，对未变化的授权范围可跨对话复用，不要求每次对话重复确认。事实版本、用途或授权范围变化，或用户撤回同意后，须重新取得相应授权；没有有效授权时不发起外部请求。未完成这项契约前，材料助手只纳入不向外部模型发送个人事实的准备工作。

## 2. Agent 分工与联调交接

| 阶段 | 王智钦 | 庄凯堃 | 交接与结果 |
| --- | --- | --- | --- |
| P0 实现 | 筛选、去重公开通知片段，保留原文和定位，定义允许外发的字段和个人事实授权边界。核对引文、条件、缺口和候选任务依赖。 | 推进 PR #81，负责模型配置、请求组装、字段过滤、超时、响应校验与错误映射。保留允许外发的字段及引文定位信息。 | 11 月 27 日前把字段清单、片段结构、结果结构和错误约定落到可评审产物。分别提交业务与模型侧代码和测试。 |
| P0 真实模型联调 | 对照同一份公开通知逐项核验规则、缺口、引文及候选依赖，修复业务判断问题。 | 11 月 28–29 日牵头从正式 Agent 入口运行到候选计划保存，记录提交号、通知链接、模型配置、耗时、结果和异常复测。 | 调用、超时和解析问题交庄凯堃处理。规则、引文和任务依赖问题交王智钦处理。杜玉鹤提供规则预期，何慧渊引用联调证据进行验收。 |
| P1 材料助手 | 负责授权交互、选取本人已确认的事实、缺项追问，以及提供草稿和事实依据供前端审阅。用户保留编辑、接受和拒绝的决定权。 | 在新增授权契约落地后，实现草拟模型调用、结构化输出和事实引用校验，验证未知事实编号、无效响应和超时。 | 对未变化且已授权的事实范围复用有效授权，不重复打断用户确认。事实版本变化或撤回后重新授权。陈常群负责前端材料交互；集成前确认导出接口负责人及与 #77 的衔接。 |

分工依据 [王智钦 #60](https://github.com/LotteryCamp/OfferPilot/issues/60) · [庄凯堃 #73](https://github.com/LotteryCamp/OfferPilot/issues/73) · [模型适配 PR #81](https://github.com/LotteryCamp/OfferPilot/pull/81)

## 3. 当前进度与验收准备

| 已有记录 | 本轮仍需的证据 |
| --- | --- |
| 多用户后端已合并，包含注册、登录、会话及个人工作区机制。 [PR #59](https://github.com/LotteryCamp/OfferPilot/pull/59) | 浏览器认证、退出或会话失效、双账号对业务接口的读写隔离。 |
| 模型适配 PR #81 为草稿。作者记录 13 项适配器测试通过，覆盖配置、超时、响应解析及部分服务异常。 [#73 进度](https://github.com/LotteryCamp/OfferPilot/issues/73#issuecomment-7165699292) · [PR #81](https://github.com/LotteryCamp/OfferPilot/pull/81) | 正式 Agent 入口的真实模型结果、引文核验和经浏览器观察的失败恢复。 |
| 核心契约已记录历史公开来源样例 `FX-S4-2027-FZU-MATH`，覆盖已结束的 2027 届福大数学与统计学院校内推荐事项中的第（5）项。 [核心流程契约](https://github.com/LotteryCamp/OfferPilot/blob/722c3679c59c1a42b43d05f190fe17dd9bda8d5e/docs/development/core-flow-contract.md#固定来源输入-fx-s4-2027-fzu-math) | 该样例用于固定规则回归及真实时钟下的到期拦截。正常建任务路径需确认一份满足确认条件的公开通知，或在隔离测试库中按契约使用固定时钟并明确记录。 |
| 主分支已有候选依据版本更新，历史候选确认时可能触发 `basis_changed`。 [PR #70](https://github.com/LotteryCamp/OfferPilot/pull/70) | 旧候选确认后的过期反馈、重新生成及确认的恢复结果。 |

测试准备由 #78 汇总。使用两个独立测试账号、可重置测试库和同一测试版本。由杜玉鹤、蔡信坡提供推免联调通知的官方链接、发布主体、适用范围、关键条款和预期结果，由庄凯堃记录实际模型配置。若采用固定时钟或保存的输入，记录对应场景。在线读取、真实模型与固定输入回归分别记录结果，便于判断现场可演示范围。

## 4. 验收矩阵

负责人提供与用例对应的结果。何慧渊在 #78 归集命令、操作或测试报告，魏之皓追踪阻塞和发布决定。状态使用「通过」「失败」「待验证」「部分已测」。候选版本验收以部署或运行该版本所得的证据为准。

### P0 推免个人工作区

| 编号与场景 | 主责与协作 | 操作与预期结果 | 当前状态与证据入口 |
| --- | --- | --- | --- |
| P0-01 认证与会话 | 陈常群，李义东提供接口 | 注册并进入本人工作区，刷新后会话有效，退出或会话失效后访问受保护页面及接口。预期登录状态、页面跳转和接口反馈一致。 | 待验证，已有账户后端 [PR #59](https://github.com/LotteryCamp/OfferPilot/pull/59) · [#75](https://github.com/LotteryCamp/OfferPilot/issues/75) |
| P0-02 私有数据隔离 | 李义东，何慧渊验证 | A 建立事项和相关记录，B 使用自己的登录状态访问 A 的资源。对已开放的事项、事实、授权、来源、候选、材料和任务接口检查读写边界。预期跨账号访问被拒绝，页面切换无上个账号的数据残留。 | 待验证 [#57](https://github.com/LotteryCamp/OfferPilot/issues/57) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) |
| P0-03 建项与通知出处 | 张锦昊，蔡信坡提供来源 | 登录后新建推免事项，读取选定的公开通知，回看发布主体、适用范围及原文定位。比对展示内容和通知，检查证据不足时界面的待核对反馈。 | 待验证 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) · [#79](https://github.com/LotteryCamp/OfferPilot/issues/79) |
| P0-04 规则、引文及候选依赖 | 王智钦，杜玉鹤提供规则预期 | 将抽取要求与原文对照，检查对象、时间、材料和关键缺口。检查引文能定位到相应原文，候选任务的依赖存在于同一计划，证据不足的结论保持待核对。 | 待验证 [#60](https://github.com/LotteryCamp/OfferPilot/issues/60) · [#74](https://github.com/LotteryCamp/OfferPilot/issues/74) |
| P0-05 模型传输同意与真实联调 | 庄凯堃，王智钦核验业务结果 | 首次运行前展示当前服务商、模型、用途、字段范围与处理方式。未授予同意或已撤回时，预期运行被拒且不产生模型出站请求。用户授予一次全局公开资料传输同意后，确认在同一有效授权范围内可跨事项复用。运行中核对请求只含契约允许的目标、白名单公开范围和公开来源，不含个人事实或材料；用同一份通知从正式入口跑到候选计划保存，重新读取候选并记录版本与结果。 | 待验证 [#73](https://github.com/LotteryCamp/OfferPilot/issues/73) · [授权契约](https://github.com/LotteryCamp/OfferPilot/blob/main/docs/backend/model-transfer-consent.md) |
| P0-06 排名补录与自查 | 张锦昊，王智钦核验结果 | 在未同意或撤回同意的账号上触发自查，预期服务端阻止运行且无外发。授予全局公开资料传输同意后，运行缺少排名时的自查，补录本人确认的排名并重新检查；预期同一有效授权可复用，刷新或切页后事实和结果一致。撤回后再次运行应被阻止。 | 待验证 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) · [授权契约](https://github.com/LotteryCamp/OfferPilot/blob/main/docs/backend/model-transfer-consent.md) |
| P0-07 拒绝候选 | 张锦昊，李义东核对持久化 | 在确认前查看任务数量，拒绝一份独立候选，刷新后核对候选和任务列表。预期候选为已拒绝，任务无新增。 | 待验证 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) |
| P0-08 确认、幂等重试与读回 | 张锦昊，李义东核对持久化 | 用操作 ID 确认一份有效候选。以相同幂等键重试，预期返回相同决定和任务 ID；再以不同幂等键确认同一终态候选，预期发生冲突且不得改写决定。刷新并重登，确认只存在一份任务且状态、依赖与写入一致。 | 待验证。依据核心流程契约 A-08 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) · [核心流程契约](https://github.com/LotteryCamp/OfferPilot/blob/722c3679c59c1a42b43d05f190fe17dd9bda8d5e/docs/development/core-flow-contract.md) |
| P0-09 依据变更与过期恢复 | 张锦昊，李义东、何慧渊协作 | 生成候选后改变其依赖的事实或依据，尝试确认旧候选，核对过期提示和任务数量，再生成并确认符合条件的新候选。历史通知另做超期拦截检查。 | 待验证 [PR #70](https://github.com/LotteryCamp/OfferPilot/pull/70) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) |
| P0-10 公开 HTML 来源与读取失败 | 蔡信坡，张锦昊核对界面 | 按现有来源契约读取一份公开 HTML 通知，核对来源 URL、原文片段和定位信息。对不可访问或不受支持的 PDF 输入验证明确失败状态，不产生伪造的提取结果或引用；缺失内容保留待核对。PDF 附件解析与页码定位不属于本轮 P0 发布门槛。 | HTML 来源待验证；PDF 能力为非阻断后续项 [核心流程契约](https://github.com/LotteryCamp/OfferPilot/blob/722c3679c59c1a42b43d05f190fe17dd9bda8d5e/docs/development/core-flow-contract.md) · [#79](https://github.com/LotteryCamp/OfferPilot/issues/79) |
| P0-11 模型错误和恢复 | 庄凯堃，前后端补齐对应反馈 | 复测超时、服务异常与无效响应。在业务界面核对失败状态、恢复操作和重试后的结果。 | 部分已测，适配器作者报告 13 项通过，业务界面待验证 [#73 进度](https://github.com/LotteryCamp/OfferPilot/issues/73#issuecomment-7165699292) · [PR #81](https://github.com/LotteryCamp/OfferPilot/pull/81) |
| P0-12 页面层级与交互 | 刘谦益负责走查，张锦昊与陈常群实现 | 对照实际演示视口和较窄视口，核对工作区、来源、自查、候选及任务页。预期当前状态和下一步易找，重复卡片和无效留白得到处理，加载、空态、失败、待核对状态清楚。 | 待验证 [#72](https://github.com/LotteryCamp/OfferPilot/issues/72) · [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) |
| P0-13 启动、恢复与回归 | 佘博海提供环境，何慧渊归集验收 | 在干净环境按说明执行迁移及启动，复核演示数据的备份和恢复。对候选版本提供同一提交号下的主流程和关键异常回归结果。 | 待验证 [#77](https://github.com/LotteryCamp/OfferPilot/issues/77) · [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) |

### P1 竞赛与个人材料

| 编号与场景 | 主责与协作 | 操作与预期结果 | 当前状态 |
| --- | --- | --- | --- |
| P1-01 单一竞赛事项 | 杜玉鹤，蔡信坡提供来源 | 用一份公开竞赛通知创建事项，核对阶段、适用对象、截止日期和材料要求。用户确认后只为当前事项生成个人任务。 | 样例待确认，集成待 11 月 30 日决定 [#74](https://github.com/LotteryCamp/OfferPilot/issues/74) |
| P1-02 材料授权与草拟 | 王智钦负责授权与业务，庄凯堃负责模型侧 | 集成前先扩充授权契约，向用户披露传输用途和字段；同意绑定明确选择的事实及其版本。相同已授权事实可跨对话复用；事实版本、用途或授权范围变化，或同意撤回时，阻止发送并重新取得授权。分别验证无授权、撤回、缺事实、未知事实编号和无效回包。有效草稿可回看事实依据并由用户编辑或拒绝。 | 授权契约未覆盖个人事实，需先补契约再决定 11 月 30 日是否集成 [#60](https://github.com/LotteryCamp/OfferPilot/issues/60) · [#73](https://github.com/LotteryCamp/OfferPilot/issues/73) · [授权契约](https://github.com/LotteryCamp/OfferPilot/blob/main/docs/backend/model-transfer-consent.md) |
| P1-03 草稿审阅与导出 | 陈常群负责前端交互，导出接口主责待定 | 编辑、接受或拒绝草稿。授权范围有效时，接受后的 DOCX 可打开且与保存文本一致；导出结果仅供本人访问。拒绝后的状态正确。 | 集成、事实授权契约及导出接口主责待确认 [#75](https://github.com/LotteryCamp/OfferPilot/issues/75) · [#77](https://github.com/LotteryCamp/OfferPilot/issues/77) |

本轮复验承接此前已关闭的 Alpha 工作，包括模型适配、核心前端、来源与审阅以及验收，分别对应 Beta 的 #73、#75、#76 和 #78。 [Alpha #29](https://github.com/LotteryCamp/OfferPilot/issues/29) · [Alpha #31](https://github.com/LotteryCamp/OfferPilot/issues/31) · [Alpha #32](https://github.com/LotteryCamp/OfferPilot/issues/32) · [Alpha #34](https://github.com/LotteryCamp/OfferPilot/issues/34)

证据至少能回答四个问题。在哪个版本和环境执行了哪条用例，输入是什么，实际结果是什么，在哪里能查看原始记录。失败项同时登记阻塞现象、主责人和复测条件。真实模型记录补充通知链接、耗时及不含密钥的配置。P0 的来源范围按核心流程契约执行，PDF 附件能力不作为当前 Beta 的通过条件。

## 5. 风险与范围决定

| 风险或待定项 | 责任人 | 解除条件与检查时间 |
| --- | --- | --- |
| 真实登录后的工作区联调和双账号隔离缺少同版本证据 | 陈常群、李义东 | 11 月 28 日完成登录至建项的冒烟，12 月 1 日补齐双账号隔离和会话回归。 |
| Agent 真实模型与领域校验已拆分，仍需共享输入及验收版本 | 庄凯堃、王智钦，杜玉鹤提供样例 | 11 月 27 日给出字段约定及来源，11 月 28–29 日共用同一通知完成真实调用和逐条规则核对。 |
| 历史样例已过截止日期，旧候选可能因依据版本变更而过期 | 杜玉鹤、张锦昊、何慧渊 | 走查中验证过期场景。正常确认选用符合条件的来源，或在隔离测试库按契约记录固定时钟结果。 |
| 已应用旧迁移的开发库与候选版本可能存在差异 | 佘博海 | 11 月 29 日给出新库启动与旧开发环境处理记录，12 月 2 日确认演示数据可恢复。 |
| 当前来源契约只承诺公开 HTML，PDF 解析尚未纳入本轮 P0 | 蔡信坡、魏之皓 | P0 验收 HTML 提取与失败反馈。#79 的 PDF 能力单独跟踪，不阻断 Beta 发布判断。 |
| P1 个人材料调用涉及当前授权契约未覆盖的个人事实 | 魏之皓、王智钦、庄凯堃 | 11 月 30 日前先确认授权契约、用户披露、版本绑定、撤回和跨对话复用语义，再决定是否开发；导出接口主责同时确认。 |

| 日期 | 范围或分工决定 | 依据 |
| --- | --- | --- |
| 11 月 26 日 | 推免为最低交付。竞赛限一个样例。材料助手根据 P0 结果纳入。 | [Beta 里程碑](https://github.com/LotteryCamp/OfferPilot/milestone/2) |
| 11 月 26 日 | 公开上下文与规则核对由王智钦负责。模型请求组装及真实联调由庄凯堃牵头。材料模块按授权流程和模型调用划分；用户级公开资料同意可复用，个人事实授权契约待扩展。 | [#60](https://github.com/LotteryCamp/OfferPilot/issues/60) · [#73](https://github.com/LotteryCamp/OfferPilot/issues/73) · [授权契约](https://github.com/LotteryCamp/OfferPilot/blob/main/docs/backend/model-transfer-consent.md) |
| 11 月 30 日 | 待记录各 P1 项继续或暂停及剩余风险。 | 11 月 29 日主流程走查记录 |

## 6. PM 每日检查与发布判断

| 日期 | 魏之皓负责 | 可留存的产物 |
| --- | --- | --- |
| 11 月 26 日 | 维护验收基线，确认单一竞赛样例范围和 Agent 职责。 | 本文件的 PR，关联 #71。 |
| 11 月 27 日 | 核对每项 P0 是否有主责、实现或测试入口和验收预期。 | 当日阻塞、负责人、下一次检查时间。 |
| 11 月 28 日 | 查看真实登录态下建项、读公告和回看出处的冒烟，检查真实模型联调是否已运行。 | 运行版本、来源链接、初步结果和缺陷项。 |
| 11 月 29 日 | 组织完整走查，确认排名、自查、候选确认与拒绝、任务读回以及异常状态。 | P0 通过、失败、待验证清单，关键问题的负责人及复测条件。 |
| 11 月 30 日 | 冻结 P0 功能范围，记录两个 P1 项各自是否继续集成。 | 范围决定及依据，更新相关风险和遗留项。 |
| 12 月 1 日 | 依据 #78 的验收记录作出发布候选准入判断。 | Go 或 No-Go 结论、候选提交、阻断项和复测条件。 |
| 12 月 2 日 | 复核候选版本与变更后的回归，锁定彩排路线、演示样例和恢复步骤。 | 候选提交、回归报告、演示步骤、已知限制。 |
| 12 月 3 日 | 归档 Beta 发布摘要和成员实际交付。 | 最终版本、通过和未通过范围、演示证据、后续 Issue 及 11 人贡献链接。 |

走查按「登录 → 建项 → 读通知并回看出处 → 查看缺口 → 补录排名并重新自查 → 审阅候选 → 确认 → 重登回读任务」执行。拒绝、跨账号访问和过期候选使用独立数据验证。页面和 Agent 采用同一候选版本的证据。

**Go** 表示 P0 验收均有通过记录，可按完整推免工作区交付。**No-Go** 表示仍有 P0 失败或待验证项，记录本次可展示的能力、阻塞项、负责人和复测条件。候选版本变更后补做受影响场景的回归。P1 逐项列入实际通过的发布范围。

| 节点 | 版本与证据 | 决策和后续 |
| --- | --- | --- |
| 12 月 1 日 · 候选准入 | 待填候选提交号、通过项、失败项、待验证项及证据 | 待填 Go 或 No-Go、P1 纳入项、负责人和复测条件 |
| 12 月 2 日 · 彩排与冻结 | 待填冻结版本、回归报告、演示数据和恢复记录 | 待填演示路线、限制及应对方式 |
| 12 月 3 日 · 发布摘要 | 待填最终版本、测试报告、截图或演示录像及贡献链接 | 待填实际交付范围、失败与未测项、后续 Issue |

## 7. 成员交付归档

| 成员 | 提交与证据入口 | 核对记录 |
| --- | --- | --- |
| 魏之皓 | 验收基线、范围决定、发布结论 [#71](https://github.com/LotteryCamp/OfferPilot/issues/71) | 文档已整理，PR 链接待补 |
| 刘谦益 | 原型、实现对照与界面走查 [#72](https://github.com/LotteryCamp/OfferPilot/issues/72) | 待补 |
| 王智钦 | Agent 业务实现 PR 与领域核验结果 [#60](https://github.com/LotteryCamp/OfferPilot/issues/60) | 待补 |
| 庄凯堃 | 模型侧 PR、真实联调记录 [#73](https://github.com/LotteryCamp/OfferPilot/issues/73) | [Draft PR #81](https://github.com/LotteryCamp/OfferPilot/pull/81)，真实模型证据待补 |
| 杜玉鹤 | 推免规则回归与竞赛样例 [#74](https://github.com/LotteryCamp/OfferPilot/issues/74) | 待补 |
| 陈常群 | 注册登录、账户态与页面联调 [#75](https://github.com/LotteryCamp/OfferPilot/issues/75) | 待补 |
| 张锦昊 | 推免主流程、页面重排与运行记录 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) | 待补 |
| 李义东 | 认证、工作区隔离及异常回归 [#57](https://github.com/LotteryCamp/OfferPilot/issues/57) | [PR #59 已合并](https://github.com/LotteryCamp/OfferPilot/pull/59)，联合验收待补 |
| 佘博海 | 迁移、启动与恢复记录 [#77](https://github.com/LotteryCamp/OfferPilot/issues/77) | 待补 |
| 何慧渊 | 测试矩阵、自动化和发布回归 [#78](https://github.com/LotteryCamp/OfferPilot/issues/78) | 待补 |
| 蔡信坡 | 公开通知、附件提取与页码定位 [#79](https://github.com/LotteryCamp/OfferPilot/issues/79) | 待补 |

## 8. 仓库提交

提交路径为仓库根目录的 `beta-release-tracking.md`，作为项目跟踪材料维护，不放入 `docs/`。首个 PR 纳入验收基线，正文使用 `Refs #71`。后续根据 #78 的结果更新验收状态、发布摘要和贡献链接，归档后更新 #71 的完成状态。
