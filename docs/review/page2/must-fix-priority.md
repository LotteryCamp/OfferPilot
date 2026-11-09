# OfferPilot Page 2 本轮必改问题清单（真实实测更新版）

> 2026-11-09（Asia/Shanghai）／v4 真实浏览器复测
> 本轮只读访问原始 Page 2，未修改 Figma、未发送消息、未提交 Git。浏览器中的合成演示不等于真实数据处理、真实 DOCX 导出或上线功能验收。
> 本文最新结论以本轮真实PNG、坐标动作及URL记录为准。旧版“等待登录／55条未执行／确认缺陷0”等是历史状态，不再作为当前结论。


用途：额度有限时，刘谦益先修4项P1，再处理P2。已经实点正确的路径只做回归，不重复生成页面。所有修改前先核对当前节点，若已修复则补证后关闭。

## LIVE-01 导出前缺少本次采用的高风险事实逐项二次核对

- Page2节点：[332:29594](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29594)、[332:29838](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29838)。
- 实际复现：按材料流程先确认合成职责，加入差异审阅并接受建议；在已接受画面点“导出副本”。接受画面说明“仅确认副本文本版本”，点击导出后直接进入“模拟完成”。已测路径没有展示本次采用的个人贡献字段的导出前逐项二次核对。
- 最小修改：在现有已接受页面展开核对区或加轻量确认层即可。示例字段“个人贡献：课程信息录入页面、字段校验、接口联调；F02；本人确认；本次再次核对”。完成后按钮才进入模拟导出。没有采用的姓名、成绩等无需凑齐八个空字段。
- 必须达到：导出前呈现本次实际采用的高风险字段、事实来源、内容及确认状态。事实首次确认、接受表达与导出前再次核对含义分开；取消核对不进入模拟完成。
- 复测：RT-01：职责确认→接受→导出；未核对时不完成；取消保留v2；再次逐项核对后到模拟完成；v1只读且没有对外提交。
- 证据：[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)。
- 状态：已确认问题／未修复复测；仅确认已测导出分支的控制缺口；未判定真实文件曾被生成或原件被覆盖。

## LIVE-02 通知确认后进入材料页未保持新增材料影响

- Page2节点：[332:30544](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30544)、[332:30844](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30844)、[314:1098](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1098)。
- 实际复现：事项概览→查看变更→确认适用并更新→新版任务→归档记录→顶部“材料写作台”。新版概览与任务显示新增真实性承诺书T08，材料统计1/4；新版归档点击材料标签进入314:1098，仍只列个人简历、成绩单、排名证明三项，没有承诺书或新版影响标识。
- 最小修改：补最小“v1.1材料清单”状态并将新版归档、概览、任务的材料入口接入；承诺书与T08互相定位。不要伪造已有个人陈述已接受或已导出的记录。
- 必须达到：同一通知演示分支内材料清单包含新增承诺书，标明S04 v1.1 §2与“待准备／需复核”，保留原件、已有版本和非受影响项；导航不能静默回旧状态。
- 复测：RT-02：稍后核对仍旧版；确认后检查任务、材料、归档、时间总览、工作台及重入；四份材料及T08一致，官方09.10与建议09.09分开。
- 证据：[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[040 notice-affected-materials](evidence/live-browser/040-notice-affected-materials.png)。
- 状态：已确认问题／未修复复测；047–049已验证新版日历、工作台与重入日期正确，不要求重做它们；仅定位已测材料入口。

## LIVE-03 新建事项进入来源后混入既有演示上下文

- Page2节点：[332:28515](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28515)、[332:28627](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28627)、[314:613](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-613)、[314:713](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-713)。
- 实际复现：新建工作区→填入示例→创建→新卡片“进入工作区”→来源与条件→后续Agent候选计划。新事项概览名为“本校推免资格核对·新建示例”，声明不沿用其他事项完成状态；来源页标题丢失“新建示例”，后续候选计划展示既有五项且T01已完成。中途没有明确切换演示场景。
- 最小修改：优先复用组件补新事项分支并连接来源／追问／计划；或在新概览明确结束本段演示，提供有说明的“切换到已有示例”入口。后者只修演示误导，完整首次创建主线仍需补齐。
- 必须达到：从新事项正常导航时保持事项名、年度、范围与初始进度；若复用既有示例，先明确提示“离开新建示例，进入已有事项演示”，不能冒充新事项后续状态。
- 复测：RT-03：工作台新卡片→来源→排名→计划→任务→返回概览，所有画面保留新事项身份，确认前无凭空已有完成项。
- 证据：[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)。
- 状态：已确认问题／未修复复测；这是原型上下文不连续，不据此宣称真实后端发生跨事项数据泄露。

## LIVE-04 排名本人确认后，待处理与任务仍表示缺排名

- Page2节点：[332:28756](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28756)、[332:28873](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28873)、[314:1395](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1395)、[332:29006](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29006)。
- 实际复现：来源与条件→补充排名信息→本人确认18/120及合成F03证明→点击Agent待处理→审阅并确认计划。来源结果已显示“按现有信息符合”、本人已确认18/120及F03；Agent待处理仍要求补排名证明，任务T02仍“待补充”。没有解释数值与证明是否有独立确认。
- 最小修改：将已确认排名分支接到对应待处理／任务状态；不把确认一项等同整体资格符合。若确需独立核验证明，调整提示为“排名数值已确认；证明X仍缺”，保留真实依据。
- 必须达到：本人确认结果与相关待办一致。若数值已确认而证明仍待补，必须分别标注两者及剩余缺口，不能同时声称同一F03已确认和仍缺失。其他未核实条件仍保留。
- 复测：RT-04：确认排名→概览→Agent→任务→返回来源，排名及证明状态不倒退，其他适用范围和纪律记录仍待核对；取消补录不改变状态。
- 证据：[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[012 agent-pending](evidence/live-browser/012-agent-pending.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)。
- 状态：已确认问题／未修复复测；不要求静态原型具备后端持久化；允许预设状态，但正常导航的表达必须一致。

## 额度有余再做

- **LIVE-05 后台任务表在1280宽Responsive模式下看不到操作列**：优先将操作列固定在右侧，压缩次要列或设表格局部滚动；与标题、筛选和搜索区保持可达。1920时表格右侧空白为次要优化。
- **LIVE-06 知识与规则首行“查看记录”点击后没有可见反馈**：连接已有记录详情；若尚无详情，仅补一张最小来源记录画面和返回入口。不要把公开来源治理改成人工审核发布，也不加入个人正文。
- **LIVE-07 T07义务性质使用“Agent建议”，偏离统一四类**：T07改为“自主可选（Agent建议）”，计数相应更新；保留非官方义务说明。无官方依据不得改成官方建议。其他类型覆盖另行补证，先不重画已修主线。

如果现场用1280桌面演示后台，LIVE-05应在演示前处理。完整四类、非推免模板和必要模板后台仍是产品范围／交付待补项；尚无全文件缺失证据时先提供已有节点，不让Agent盲目重画。不能据本清单宣称整个正式产品P0已验收。

## 本轮无需重做的已核实内容

- 创建入口、空表单必填、填入预设、创建成功和新卡片进入。
- 候选计划不采用保留5项；采用进入7项。重复确认和撤销仍待测。
- 材料首次事实确认、拒绝／重审／接受、原v1保留、明确模拟DOCX、归档及回写作台。
- 旧概览同时提醒新截止，稍后不擅改；采用后任务／归档／日历／工作台／重入保持09.10（材料入口例外见LIVE-02）。
- 后台自动来源治理文案与AG-1048脱敏异常详情。

修复后由真实执行者按RT-01～04补前后截图、节点、时间和结论；不得仅凭“Agent已完成”关闭。完整依据见[审查包问题清单](issue-log.md)。
