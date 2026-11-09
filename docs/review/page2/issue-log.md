# OfferPilot Page 2 第二轮问题与复核清单（v4实测）

> 2026-11-09（Asia/Shanghai）／v4 真实浏览器复测
> 本轮只读访问原始 Page 2，未修改 Figma、未发送消息、未提交 Git。浏览器中的合成演示不等于真实数据处理、真实 DOCX 导出或上线功能验收。
> 本文最新结论以本轮真实PNG、坐标动作及URL记录为准。旧版“等待登录／55条未执行／确认缺陷0”等是历史状态，不再作为当前结论。


## 最新结论与处理顺序

55条原用例的当前状态：已测不通过7条；部分执行26条；未执行20条；原型分支通过2条。三条代表场景均已进行真实业务点击并到达关键结果态；均仍有未满足项，端到端整体验收通过0。局部成功步骤和失败步骤分别记录，不能用“完成走查”代替验收通过。

优先修LIVE-01～04。LIVE-05～07额度有余再做；若答辩将在1280窗口演示后台，应提前修LIVE-05。模板、三层信息、版本恢复等仍待补证，不能因未验证自动要求重画。

|编号|优先级|已确认的原型问题|范围与证据|
|---|---|---|---|
|LIVE-01|P1|导出前缺少本次采用的高风险事实逐项二次核对|[332:29594](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29594)、[332:29838](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29838)；[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)|
|LIVE-02|P1|通知确认后进入材料页未保持新增材料影响|[332:30544](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30544)、[332:30844](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30844)、[314:1098](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1098)；[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[040 notice-affected-materials](evidence/live-browser/040-notice-affected-materials.png)|
|LIVE-03|P1|新建事项进入来源后混入既有演示上下文|[332:28515](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28515)、[332:28627](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28627)、[314:613](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-613)、[314:713](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-713)；[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)|
|LIVE-04|P1|排名本人确认后，待处理与任务仍表示缺排名|[332:28756](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28756)、[332:28873](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28873)、[314:1395](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1395)、[332:29006](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29006)；[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[012 agent-pending](evidence/live-browser/012-agent-pending.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)|
|LIVE-05|P2|后台任务表在1280宽Responsive模式下看不到操作列|[314:2452](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-2452)；[062 open-options-fast](evidence/live-browser/062-open-options-fast.png)、[063 enable-responsive-mode](evidence/live-browser/063-enable-responsive-mode.png)、[067 responsive-admin-return-list](evidence/live-browser/067-responsive-admin-return-list.png)、[069 admin-table-horizontal-scroll](evidence/live-browser/069-admin-table-horizontal-scroll.png)、[070 admin-table-bottom](evidence/live-browser/070-admin-table-bottom.png)、[072 admin-table-responsive-1440](evidence/live-browser/072-admin-table-responsive-1440.png)、[073 admin-table-responsive-1920](evidence/live-browser/073-admin-table-responsive-1920.png)|
|LIVE-06|P2|知识与规则首行“查看记录”点击后没有可见反馈|[314:2100](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-2100)；[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)、[052 admin-source-record](evidence/live-browser/052-admin-source-record.png)、[053 admin-source-record-arrow](evidence/live-browser/053-admin-source-record-arrow.png)|
|LIVE-07|P2|T07义务性质使用“Agent建议”，偏离统一四类|[314:713](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-713)、[332:29006](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29006)；[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)|

### LIVE-01 导出前缺少本次采用的高风险事实逐项二次核对

- 分类／优先级：已确认的所测原型路径／画面问题；P1。
- Page／节点：Page 2；[332:29594](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29594)、[332:29838](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29838)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：按材料流程先确认合成职责，加入差异审阅并接受建议；在已接受画面点“导出副本”。
- 实际：接受画面说明“仅确认副本文本版本”，点击导出后直接进入“模拟完成”。已测路径没有展示本次采用的个人贡献字段的导出前逐项二次核对。
- 预期：导出前呈现本次实际采用的高风险字段、事实来源、内容及确认状态。事实首次确认、接受表达与导出前再次核对含义分开；取消核对不进入模拟完成。
- 建议修改：在现有已接受页面展开核对区或加轻量确认层即可。示例字段“个人贡献：课程信息录入页面、字段校验、接口联调；F02；本人确认；本次再次核对”。完成后按钮才进入模拟导出。没有采用的姓名、成绩等无需凑齐八个空字段。
- 复测用例：RT-01：职责确认→接受→导出；未核对时不完成；取消保留v2；再次逐项核对后到模拟完成；v1只读且没有对外提交。
- 依据：正式方案 L220、L225、L246，尤其 L246 的“在导出前逐项确认”。
- 证据：[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)。
- 关联原用例：M09。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。仅确认已测导出分支的控制缺口；未判定真实文件曾被生成或原件被覆盖。

### LIVE-02 通知确认后进入材料页未保持新增材料影响

- 分类／优先级：已确认的所测原型路径／画面问题；P1。
- Page／节点：Page 2；[332:30544](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30544)、[332:30844](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-30844)、[314:1098](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1098)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：事项概览→查看变更→确认适用并更新→新版任务→归档记录→顶部“材料写作台”。
- 实际：新版概览与任务显示新增真实性承诺书T08，材料统计1/4；新版归档点击材料标签进入314:1098，仍只列个人简历、成绩单、排名证明三项，没有承诺书或新版影响标识。
- 预期：同一通知演示分支内材料清单包含新增承诺书，标明S04 v1.1 §2与“待准备／需复核”，保留原件、已有版本和非受影响项；导航不能静默回旧状态。
- 建议修改：补最小“v1.1材料清单”状态并将新版归档、概览、任务的材料入口接入；承诺书与T08互相定位。不要伪造已有个人陈述已接受或已导出的记录。
- 复测用例：RT-02：稍后核对仍旧版；确认后检查任务、材料、归档、时间总览、工作台及重入；四份材料及T08一致，官方09.10与建议09.09分开。
- 依据：方案变化监测与影响分析、材料清单与状态一致性；本轮场景③明确要求。
- 证据：[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[040 notice-affected-materials](evidence/live-browser/040-notice-affected-materials.png)。
- 关联原用例：N04。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。047–049已验证新版日历、工作台与重入日期正确，不要求重做它们；仅定位已测材料入口。

### LIVE-03 新建事项进入来源后混入既有演示上下文

- 分类／优先级：已确认的所测原型路径／画面问题；P1。
- Page／节点：Page 2；[332:28515](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28515)、[332:28627](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28627)、[314:613](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-613)、[314:713](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-713)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：新建工作区→填入示例→创建→新卡片“进入工作区”→来源与条件→后续Agent候选计划。
- 实际：新事项概览名为“本校推免资格核对·新建示例”，声明不沿用其他事项完成状态；来源页标题丢失“新建示例”，后续候选计划展示既有五项且T01已完成。中途没有明确切换演示场景。
- 预期：从新事项正常导航时保持事项名、年度、范围与初始进度；若复用既有示例，先明确提示“离开新建示例，进入已有事项演示”，不能冒充新事项后续状态。
- 建议修改：优先复用组件补新事项分支并连接来源／追问／计划；或在新概览明确结束本段演示，提供有说明的“切换到已有示例”入口。后者只修演示误导，完整首次创建主线仍需补齐。
- 复测用例：RT-03：工作台新卡片→来源→排名→计划→任务→返回概览，所有画面保留新事项身份，确认前无凭空已有完成项。
- 依据：单人多事项隔离、当前事项范围与首次创建主线。
- 证据：[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)。
- 关联原用例：C01、U01。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。这是原型上下文不连续，不据此宣称真实后端发生跨事项数据泄露。

### LIVE-04 排名本人确认后，待处理与任务仍表示缺排名

- 分类／优先级：已确认的所测原型路径／画面问题；P1。
- Page／节点：Page 2；[332:28756](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28756)、[332:28873](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-28873)、[314:1395](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-1395)、[332:29006](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29006)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：来源与条件→补充排名信息→本人确认18/120及合成F03证明→点击Agent待处理→审阅并确认计划。
- 实际：来源结果已显示“按现有信息符合”、本人已确认18/120及F03；Agent待处理仍要求补排名证明，任务T02仍“待补充”。没有解释数值与证明是否有独立确认。
- 预期：本人确认结果与相关待办一致。若数值已确认而证明仍待补，必须分别标注两者及剩余缺口，不能同时声称同一F03已确认和仍缺失。其他未核实条件仍保留。
- 建议修改：将已确认排名分支接到对应待处理／任务状态；不把确认一项等同整体资格符合。若确需独立核验证明，调整提示为“排名数值已确认；证明X仍缺”，保留真实依据。
- 复测用例：RT-04：确认排名→概览→Agent→任务→返回来源，排名及证明状态不倒退，其他适用范围和纪律记录仍待核对；取消补录不改变状态。
- 依据：四态自查、确认机制及跨页状态保持。
- 证据：[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[012 agent-pending](evidence/live-browser/012-agent-pending.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)。
- 关联原用例：U05、C08。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。不要求静态原型具备后端持久化；允许预设状态，但正常导航的表达必须一致。

### LIVE-05 后台任务表在1280宽Responsive模式下看不到操作列

- 分类／优先级：已确认的所测原型路径／画面问题；P2。
- Page／节点：Page 2；[314:2452](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-2452)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：Present选项从Actual size切到Responsive；后台Agent任务列表分别调整为1280×900、1440×1000、1920×1080；1280下尝试横向滚动并查看表底。
- 实际：1280时“操作／查看异常”列不可见，尝试滚动未恢复可见入口；1440及1920可见。异常详情自身有宽度适应，不能泛化全站不响应式。
- 预期：窄桌面仍能查看异常。允许表格局部横向滚动、固定操作列或折叠次要字段，不能仅把整张原型缩小当适配。
- 建议修改：优先将操作列固定在右侧，压缩次要列或设表格局部滚动；与标题、筛选和搜索区保持可达。1920时表格右侧空白为次要优化。
- 复测用例：RT-05：三个宽度在Responsive下从AG-1048进入详情并返回；1280操作列可达，长内容无不可恢复裁切。
- 依据：本轮PC Web多宽度审查要求及U03验收约定。
- 证据：[062 open-options-fast](evidence/live-browser/062-open-options-fast.png)、[063 enable-responsive-mode](evidence/live-browser/063-enable-responsive-mode.png)、[067 responsive-admin-return-list](evidence/live-browser/067-responsive-admin-return-list.png)、[069 admin-table-horizontal-scroll](evidence/live-browser/069-admin-table-horizontal-scroll.png)、[070 admin-table-bottom](evidence/live-browser/070-admin-table-bottom.png)、[072 admin-table-responsive-1440](evidence/live-browser/072-admin-table-responsive-1440.png)、[073 admin-table-responsive-1920](evidence/live-browser/073-admin-table-responsive-1920.png)。
- 关联原用例：U03。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。060的Actual size裁切不作为响应式缺陷；有效证据从063选择Responsive后开始。

### LIVE-06 知识与规则首行“查看记录”点击后没有可见反馈

- 分类／优先级：已确认的所测原型路径／画面问题；P2。
- Page／节点：Page 2；[314:2100](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-2100)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：后台运行概览→知识与规则；点S01首行“查看记录”文字，再点右箭头，等待页面反馈。
- 实际：两次点击后URL和画面均未变化，截图与点击前相同。旁边Agent任务菜单及异常详情可正常跳转。
- 预期：打开对应来源记录（发布单位、适用范围、版本、获取时间、原文位置及异常）；未实现的演示入口应明确标“仅展示”，而非无反馈链接。
- 建议修改：连接已有记录详情；若尚无详情，仅补一张最小来源记录画面和返回入口。不要把公开来源治理改成人工审核发布，也不加入个人正文。
- 复测用例：RT-06：S01查看记录→核对来源ID/版本/范围→返回原筛选列表；其他记录未连线时明确演示范围。
- 依据：来源可追溯、按钮反馈和必要后台审查。
- 证据：[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)、[052 admin-source-record](evidence/live-browser/052-admin-source-record.png)、[053 admin-source-record-arrow](evidence/live-browser/053-admin-source-record-arrow.png)。
- 关联原用例：U01、B01。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。只确认该已测入口无可见响应；没有读取原生reaction，不能断言所有记录均无连接。

### LIVE-07 T07义务性质使用“Agent建议”，偏离统一四类

- 分类／优先级：已确认的所测原型路径／画面问题；P2。
- Page／节点：Page 2；[314:713](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-713)、[332:29006](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-29006)。图层原始画框名未读取，以页面可见标题及节点定位。
- 复现：审阅候选计划→确认并加入任务→查看T07及任务性质计数。
- 实际：T07显示“Agent建议，非官方义务”，计数为“6项官方必需／1项Agent建议”。没有伪装成官方要求，但未使用方案的四类枚举。
- 预期：义务性质限定官方必需／官方建议／自主可选／待核实；Agent是建议产生者，可作为附加来源，不是第五种性质。
- 建议修改：T07改为“自主可选（Agent建议）”，计数相应更新；保留非官方义务说明。无官方依据不得改成官方建议。其他类型覆盖另行补证，先不重画已修主线。
- 复测用例：RT-07：候选与已加入列表的义务标签一致；执行状态仍独立；可选不被表现为必做。
- 依据：正式方案L118–123固定四类；完整四类交付仍见DOC-02。
- 证据：[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)。
- 关联原用例：X11。
- 当前复测状态：问题已真实复现，尚未修复复测关闭。只确认所见枚举不一致，不从单个画面推断其他三类在全文件不存在。

## 原DOC问题的最新复核

|历史项|本轮已取得的结果|剩余处理／定性|
|---|---|---|
|DOC-00 Page1旧图|新增75张真实Page2过程截图和节点轨迹|原ZIP旧图事实保留；本轮覆盖的状态补证，未覆盖状态仍需索引|
|DOC-01 创建说明|必填、预设、成功和进入新事项已实点|取消、失败、重试、无官方来源仍未测；另见LIVE-03|
|DOC-02 四类义务|已见T07非官方义务|枚举问题见LIVE-07；完整四类可操作覆盖仍待验证|
|DOC-03 非推免场景|工作台仍明确其他卡片仅展示|产品首版双场景范围缺口保留，不凭此否定已测推免子流程|
|DOC-04 材料控制|追问、事实确认、拒绝／接受、模拟DOCX及归档已实点|二次核对确证见LIVE-01；完整预览、多项独立选择、历史恢复仍待验证|
|DOC-05 通知影响|日期、T08、更新归档与新版日历／工作台／重入已证实|材料入口确证见LIVE-02；幂等、撤销及旧材料需复核标记未测|
|DOC-06 模板管理|已见来源列表与异常详情|未到达模板列表／详情；不能据此确认整个文件无模板，先提供确切入口|
|DOC-07 信息分层|个人空间及后台脱敏说明可见|私有线索与个人档案复用、真实隔离／请求行为未验证|
|DOC-08 停止撤销防重|计划采用／不采用真实可达；异常只见详情|停止、技术重试、重复确认、撤销仍未执行|
|DOC-09 桌面适配|后台详情／列表已有三宽度证据|列表1280见LIVE-05；材料仅1440，200%及键盘未测|

### 待验证风险的更新

|编号|v4结论|剩余范围|
|---|---|---|
|RISK-01|本次旧概览033同时提醒v1.1与09.10，所测分支不构成旧日期无提醒；不要求重做|其他入口的提醒一致性未全测|
|RISK-02|拒绝保持5项，确认进入7项；计数子路径已验证|重复确认、撤销、全部返回路径待测|
|RISK-03|所测材料追问与表达接受分开，拒绝不会伪造已接受归档|其他入口绕行、历史恢复、多项独立决定仍待测；导出二次核对见LIVE-01|
|RISK-04|后台AG-1048失败步骤及保留检查点有真实画面|学生端恢复、停止、防重未测|

### 第一轮14项的关闭口径

以下均限定于已测Page2原型，不等于真实系统验收。旧完整追踪见历史记录。

|历史编号|v4结论|
|---|---|
|R2-I01|入口／必填／示例／成功可用；新事项后续上下文仍有LIVE-03，未整体关闭|
|R2-I02|确认与不采纳子路径可用；撤销防重未验证，部分复核|
|R2-I03|预设个人陈述追问到本人确认草稿实点可用，所测子路径通过；不代表真实Agent推理已验证|
|R2-I04|模拟导出画面明确DOCX副本且未生成文件；所测格式文案已修，真实DOCX另测|
|R2-I05|左右差异、拒绝、接受、v1保留及归档已见；完整文件、恢复、多项独立待测|
|R2-I06|日期、任务、归档等多处已验证；材料入口LIVE-02，未整体关闭|
|R2-I07|知识页自动处理、非人工审核发布前置文案已核实；不判旧Page1缺陷仍在|
|R2-I08|异常详情只描述技术失败与脱敏边界；所测画面未要求管理员裁决政策，其他入口未全验|
|R2-I09|异常详情可达；首行来源记录LIVE-06；模板入口待补证|
|R2-I10|四态图例与18/120=15%已核实，负面实际分支未测|
|R2-I11|通知分支官方09.10与建议09.09区分已核实，手改个人日期未测|
|R2-I12|所测旧概览同时展示待核对新截止，所测提醒疑点消除|
|R2-I13|其他卡片仅展示、个人空间可见；完整非推免主线和档案复用待补|
|R2-I14|后台三宽度部分复核；LIVE-05与材料多宽度待补，未关闭|

## 交给刘谦益的第二次修复后复测安排

1. 只改仍存在的问题；先核对当前节点，四项P1可通过复用状态、补小确认层和修连线完成，无需整套重画。
2. 刘谦益修完逐条填修改节点、内容、版本和时间；陈常群、张锦昊各自实际复测后填姓名，当前不得代写已完成人工复测。
3. 按RT-01～04先复测，再回归计划拒绝／确认、材料拒绝／接受、通知稍后／采用；最后补RT-05～07。
4. 回归时保存操作前后真实PNG和目标节点，核对正常导航不会回旧状态；查看器Next不能替代产品入口。
5. 没有证据时保持“待验证”；真实DOCX、权限、模型请求隔离和后端幂等独立验收，原型模拟不冒充通过。

## 历史材料

[v3问题原文](evidence/history/v3/issue-log.md)、[TinyFish辅助日志审计](evidence/tinyfish/runtime-audit.md)、[原始导出说明](evidence/source-export/prototyping/prototype.md)。历史“待登录／零缺陷”等只适用于当时阶段。完整真实动作审计见[现场证据说明](evidence/live-browser/README.md)。
