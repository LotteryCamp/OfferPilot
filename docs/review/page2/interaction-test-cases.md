# OfferPilot Page 2 交互测试用例与实际结果（v4）

> 2026-11-09（Asia/Shanghai）／v4 真实浏览器复测
> 本轮只读访问原始 Page 2，未修改 Figma、未发送消息、未提交 Git。浏览器中的合成演示不等于真实数据处理、真实 DOCX 导出或上线功能验收。
> 本文最新结论以本轮真实PNG、坐标动作及URL记录为准。旧版“等待登录／55条未执行／确认缺陷0”等是历史状态，不再作为当前结论。


## 执行统计与口径

保留原55条定义。已测不通过7条；部分执行26条；未执行20条；原型分支通过2条。用例包含的全部关键判据均满足才能标通过；只验证到子步骤则“部分执行”。发现其中一项明确违反预期可记“已测不通过”，同时注明尚未执行的部分。预设原型通过与真实文件／权限验证分开。

三条代表场景端到端整体验收通过0；这不等于没有真实点击或所有子步骤失败。真实局部成功与未满足项如下。

|场景|实际证据顺序|结论|
|---|---|---|
|① 首次创建推免申请工作区|003→004→006→007→008→009→010→011→012→013→014→015→016|已走到创建成功、排名确认、计划拒绝及确认结果；新建事项身份与后续已有任务不连续，排名确认在后续待办中倒退。首次主线不通过；任意输入、失败重试、无来源建项尚未测。|
|② 个人材料审阅与版本|017→018→019→021→022→023→024→025→026→027→028→029→030|追问、事实确认、更新草稿、左右对照、拒绝重审、接受、模拟DOCX、归档和回写作台均真实可达。导出前二次事实核对缺口未通过；历史恢复及真实DOCX仍未执行。|
|③ 官方通知变化|031→032→033→034→035→036→037→038→039→040；046→047→048→049|稍后保留v1.0并同时提醒v1.1；确认后概览、任务、归档、新版日历、工作台及重入均有真实证据。039→040材料入口回旧清单，材料影响未通过。046是深链恢复后另段实点，不伪称一段不中断路径。|

## 55条用例

### C01 创建主线

- 分组／前置：① 首次创建推免申请工作区；新用户／无事项；使用合成资料
- 步骤：事项列表→新建→填名称、范围、年度→来源解析→追问→本人确认→候选计划→确认→任务列表
- 预期：当前本人事项正确；成功反馈明确；确认前不创建执行任务；全程可返回。
- 当前状态：**已测不通过**
- 实际结果：已点新建、空表校验、填入预设、创建并进入“新建示例”。从该页点来源后进入既有事项标题与基线任务，未明确切换场景，新建事项上下文未连续保持。
- 本轮真实证据：[002 dismiss-cookie](evidence/live-browser/002-dismiss-cookie.png)、[003 new-workspace](evidence/live-browser/003-new-workspace.png)、[004 create-empty-validation](evidence/live-browser/004-create-empty-validation.png)、[006 fill-example-correct](evidence/live-browser/006-fill-example-correct.png)、[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[012 agent-pending](evidence/live-browser/012-agent-pending.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)
- 限制／未测部分：判定限于本次原型路由与可见上下文；不推断真实跨事项数据泄露。,预设填入不等于任意输入、真实创建或来源解析能力通过。

### C02 必填与错误纠正

- 分组／前置：① 首次创建推免申请工作区；创建表单为空
- 步骤：尝试创建→查看字段错误→补齐→重试
- 预期：字段级提示；保留其他输入；不生成半成品／重复事项。
- 当前状态：**部分执行**
- 实际结果：空表点击创建出现名称、事项类型两项字段级必填提示；点击正确的“填入示例”后进入已填页并成功创建。
- 本轮真实证据：[003 new-workspace](evidence/live-browser/003-new-workspace.png)、[004 create-empty-validation](evidence/live-browser/004-create-empty-validation.png)、[006 fill-example-correct](evidence/live-browser/006-fill-example-correct.png)、[007 create-filled](evidence/live-browser/007-create-filled.png)
- 限制／未测部分：未验证任意输入、保留已填字段或重复创建防重；不将子路径扩展为完整用例通过。,第5次坐标未命中正确按钮，第6次纠正后成功，不作为按钮故障。

### C03 取消创建

- 分组／前置：① 首次创建推免申请工作区；填入部分资料但尚未确认
- 步骤：取消／返回→回到事项列表
- 预期：不创建新事项；有未保存内容时给出合理提示；不误写入。
- 当前状态：**未执行**
- 实际结果：尚未操作创建表单的取消／返回分支。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：按钮可见不等于取消不写入已验证。

### C04 创建超时与重试

- 分组／前置：① 首次创建推免申请工作区；可触发模拟失败或测试失败状态
- 步骤：创建→失败→重试→成功→再次点击确认
- 预期：有失败原因与恢复入口；幂等，不重复生成事项。
- 当前状态：**未执行**
- 实际结果：未触发创建超时、失败、重试或重复确认。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：成功创建不能替代失败恢复或幂等测试。

### C05 无官方来源创建

- 分组／前置：① 首次创建推免申请工作区；没有链接，仅提出个人目标
- 步骤：创建空事项→查看首页与条件区
- 预期：可建立本人容器；规则和官方日期待核实；无确定资格结论。
- 当前状态：**未执行**
- 实际结果：本次使用含S01/S02预设来源的示例，未执行无来源创建。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：表单说明允许稍后补来源，不等于无来源路径已测。

### C06 来源解析与范围

- 分组／前置：① 首次创建推免申请工作区；提供合成校级／学院来源
- 步骤：解析→查看学校、学院、专业、年级／年度与批次→原文
- 预期：有范围、版本、获取时间和原文定位；模板默认值不冒充政策。
- 当前状态：**部分执行**
- 实际结果：进入来源与条件页，看到S01/S02/S04、日期、年度、学院及S02§2排名依据；本轮未执行真实解析或打开完整原文。
- 本轮真实证据：[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)
- 限制／未测部分：原文链接、获取时间、范围匹配过程与解析异常未完整验证。,合成规则不是实际学校政策。

### C07 缺少排名

- 分组／前置：① 首次创建推免申请工作区；规则明确，但未提供个人排名或证明
- 步骤：生成自查→暂不补充→返回条件区
- 预期：显示待补充信息；不能因返回进入已符合状态。
- 当前状态：**部分执行**
- 实际结果：来源页及补录页均在本人确认前明确显示排名待补充，计算预览不等于已确认。
- 本轮真实证据：[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[010 rank-ask](evidence/live-browser/010-rank-ask.png)
- 限制／未测部分：尚未执行“暂不补充／取消并返回”分支，不能判完整用例通过。

### C08 本人确认事实

- 分组／前置：① 首次创建推免申请工作区；准备合成排名及证明
- 步骤：补充→核对事实和来源→确认／取消两分支
- 预期：确认后才能用于当前分析；取消不写入；个人确认不等于官方核实。
- 当前状态：**部分执行**
- 实际结果：预设18/120排名及合成证明在确认前标为未确认；点击本人确认后出现15%及“按现有信息符合”，其他待核对项保留。
- 本轮真实证据：[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)
- 限制／未测部分：取消分支未测；进入Agent页后的排名待办出现不一致，见U05。,个人确认不是学校正式认定，未检验证明真实性。

### C09 候选计划确认与不采纳

- 分组／前置：① 首次创建推免申请工作区；候选任务已生成，尚未加入
- 步骤：查看性质、来源、依赖与日期→返回／不采纳／确认
- 预期：返回和不采纳不创建执行清单；确认才加入；有成功反馈和撤销。
- 当前状态：**部分执行**
- 实际结果：候选计划列明已有五项与新增T06/T07。暂不采用返回五项；重新审阅后确认进入七项并显示确认记录。
- 本轮真实证据：[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)、[015 plan-reopen](evidence/live-browser/015-plan-reopen.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)
- 限制／未测部分：未执行计划撤销、其他返回路线或重复确认；不把确认／不采纳子步骤扩展为完整用例通过。

### C10 计划重复确认与撤销

- 分组／前置：① 首次创建推免申请工作区；已确认过同一候选计划
- 步骤：再次确认→查看任务数量→撤销→再次查看
- 预期：不重复生成；撤销范围明确并保留记录；不自动更改官方规则。
- 当前状态：**未执行**
- 实际结果：未在已经确认的同一计划上再次确认，也未执行撤销计划。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：拒绝后重新审阅再确认不是重复确认同一已加入计划的测试。

### M01 原件预览

- 分组／前置：② 个人材料检查、改稿与版本；合成简历DOCX和要求文件
- 步骤：资料列表→预览原件→查看版本和只读标识
- 预期：可读原稿；原件独立保留；不能直接覆盖。
- 当前状态：**部分执行**
- 实际结果：材料与草稿页面可读原始段落，明确v1只读、v2副本，接受后仍显示原始段落保留。
- 本轮真实证据：[017 materials-workbench](evidence/live-browser/017-materials-workbench.png)、[021 send-request-correct](evidence/live-browser/021-send-request-correct.png)、[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[025 reject-material-suggestion](evidence/live-browser/025-reject-material-suggestion.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)
- 限制／未测部分：未从文件列表打开完整DOCX预览，未验证真实文件不能覆盖。

### M02 诊断与修改范围

- 分组／前置：② 个人材料检查、改稿与版本；原稿缺个人贡献说明
- 步骤：诊断→查看要求到段落／附件映射→选择局部修改
- 预期：缺信息／表达／格式问题分开；本人决定范围，不擅自整篇改写。
- 当前状态：**部分执行**
- 实际结果：材料页显示职责缺口及F02/S02§3映射；通过预设个人陈述进入职责补充。
- 本轮真实证据：[017 materials-workbench](evidence/live-browser/017-materials-workbench.png)、[018 agent-conversation](evidence/live-browser/018-agent-conversation.png)、[019 choose-personal-statement](evidence/live-browser/019-choose-personal-statement.png)、[021 send-request-correct](evidence/live-browser/021-send-request-correct.png)、[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)
- 限制／未测部分：没有完成缺信息／表达／格式三类诊断与局部范围选择的完整路径。

### M03 Agent追问事实

- 分组／前置：② 个人材料检查、改稿与版本；未提供具体职责、排名或成果
- 步骤：提出改稿→追问→暂不提供
- 预期：未提供字段留待确认；不补造职责、成绩、论文、获奖。
- 当前状态：**部分执行**
- 实际结果：发送预设个人陈述请求后，草稿保留职责待补；进入本人确认页面前，建议职责明确为未确认、不自动写入。
- 本轮真实证据：[018 agent-conversation](evidence/live-browser/018-agent-conversation.png)、[019 choose-personal-statement](evidence/live-browser/019-choose-personal-statement.png)、[021 send-request-correct](evidence/live-browser/021-send-request-correct.png)、[022 supplement-role](evidence/live-browser/022-supplement-role.png)
- 限制／未测部分：尚未点击“暂不确认，保留待补充”分支；任意输入与真实模型响应未测。,第20次坐标未命中发送按钮，第21次纠正成功，不计为发送故障。

### M04 事实冲突与无依据增强

- 分组／前置：② 个人材料检查、改稿与版本；输入职责或日期矛盾；要求参与者改负责人
- 步骤：请求增强→检查回应→纠正→本人确认
- 预期：标出冲突，拒绝无依据增强；不能把计划写成已完成成果。
- 当前状态：**未执行**
- 实际结果：未输入冲突日期、矛盾职责或请求把参与者增强为负责人。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：页面声明不增加奖项、性能或成果，仅为可见边界，不能替代攻击／冲突样例测试。

### M05 生成停止与重试

- 分组／前置：② 个人材料检查、改稿与版本；本人已确认修改所需事实
- 步骤：生成→停止／超时→重试→建议稿
- 预期：原件不变；状态可理解；不重复生成版本或未授权继续。
- 当前状态：**未执行**
- 实际结果：未触发材料生成中的停止、超时或重试。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：点击本人确认进入更新稿不等于生成失败恢复已测；后台解析异常不替代材料生成分支。

### M06 逐项接受／拒绝

- 分组／前置：② 个人材料检查、改稿与版本；至少两项修改独立待决定
- 步骤：接受第1项→拒绝第2项→撤销第1项→再次查看
- 预期：每项选择独立；接受表达不自动确认事实；状态与文本一致。
- 当前状态：**部分执行**
- 实际结果：同一建议先拒绝后重新审阅再接受，拒绝页保留原稿与事实确认，接受页单独记录副本文本确认。
- 本轮真实证据：[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[025 reject-material-suggestion](evidence/live-browser/025-reject-material-suggestion.png)、[026 material-review-again](evidence/live-browser/026-material-review-again.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)
- 限制／未测部分：仅一项段落建议；没有至少两项独立选择及撤销第1项，不能判完整逐项控制通过。

### M07 差异与来源

- 分组／前置：② 个人材料检查、改稿与版本；已确认事实和官方要求版本
- 步骤：打开左右对照→查看高亮及理由→点引用
- 预期：原稿／建议清楚；有事实版本与要求定位；窄屏操作仍可达。
- 当前状态：**部分执行**
- 实际结果：1440视口下原始段落与建议段落左右可读，显示F02与S02§3，事实确认和文字接受分开。
- 本轮真实证据：[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[025 reject-material-suggestion](evidence/live-browser/025-reject-material-suggestion.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[075 resume-diff-responsive](evidence/live-browser/075-resume-diff-responsive.png)
- 限制／未测部分：没有点击引用打开原文；未验证至少两项高亮或窄屏差异阅读。,075为直接进入已知审阅节点，不能充当新的业务导航通过。,后续材料1280/1920操作被自动审批用量上限拒绝，未执行，不纳入证据。

### M08 版本保存与恢复

- 分组／前置：② 个人材料检查、改稿与版本；已形成v2，原件v1仍在
- 步骤：保存v2→历史→查看v1→确认恢复→查看新版本
- 预期：恢复为新版本；历史保留；取消恢复不改变当前版；返回后不丢恢复状态。
- 当前状态：**部分执行**
- 实际结果：接受后形成已确认v2，模拟导出与归档仍标明v1只读保留；返回材料台保留已确认v2。
- 本轮真实证据：[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[029 material-archive](evidence/live-browser/029-material-archive.png)、[030 return-confirmed-materials](evidence/live-browser/030-return-confirmed-materials.png)
- 限制／未测部分：没有打开版本历史、恢复旧版或取消恢复；不能证明v3恢复能力。

### M09 导出前关键事实核对

- 分组／前置：② 个人材料检查、改稿与版本；已选定审阅版本
- 步骤：逐项核对姓名、学号、成绩、排名、日期、论文状态、奖项级别、贡献→确认／返回
- 预期：关键字段逐项有依据和确认状态；待确认不静默进入定稿。
- 当前状态：**已测不通过**
- 实际结果：已测路径从接受建议页点击“导出副本”直接进入“模拟完成”，未体现对本次采用高风险事实（至少个人贡献）的导出前逐项二次核对。接受页明确仅确认副本文本版本。
- 本轮真实证据：[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[023 confirm-role-update-draft](evidence/live-browser/023-confirm-role-update-draft.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)
- 限制／未测部分：依据正式方案第246行；不要求一定新增独立页面，但需体现逐项二次确认及返回核对。,不要求确认材料未采用的全部字段；本项判定为原型控制路径缺口，不是真实导出错误。

### M10 DOCX副本与归档

- 分组／前置：② 个人材料检查、改稿与版本；导出前已确认
- 步骤：导出新DOCX→成功／失败→重试→归档→查看办理状态
- 预期：新文件含名称和版本；原件不变；已导出≠已提交；归档保留规则、材料及确认版本。真实文件检查与原型状态分记。
- 当前状态：**部分执行**
- 实际结果：导出副本进入明确标注的模拟完成页，显示个人陈述_v2_演示副本.docx；随后进入归档，保留v1/v2、F02/S02及本人确认／接受记录，说明正式提交由本人完成。
- 本轮真实证据：[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[029 material-archive](evidence/live-browser/029-material-archive.png)、[030 return-confirmed-materials](evidence/live-browser/030-return-confirmed-materials.png)
- 限制／未测部分：未测试导出失败、重试或完整本人办理记录；没有生成真实DOCX。,导出前二次核对缺口另记M09，不能将本子链路称为材料整体验收通过。

### M11 复杂格式失败

- 分组／前置：② 个人材料检查、改稿与版本；扫描件、复杂表格、公式或特殊字体
- 步骤：导入→识别限制→查看原稿／改用文本
- 预期：先说明限制；不静默损坏版面；不承诺任意文件可正确编辑。
- 当前状态：**未执行**
- 实际结果：未导入复杂表格、公式、扫描件或特殊字体材料。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：无实际格式失败／文本替代操作证据。

### M12 真实导出文件检查

- 分组／前置：② 个人材料检查、改稿与版本；仅在已有可下载真实文件时执行
- 步骤：另存副本→打开DOCX→对比文本、版式、引用→对原件做前后校验
- 预期：真实文件可打开且原件未变；只有原型画面时本用例保持未执行或能力未覆盖。
- 当前状态：**未执行**
- 实际结果：页面明确本次未生成或下载真实文件；未执行真实DOCX打开、版式与原件前后校验。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：原型导出模拟不是文件检查失败，也不能算真实DOCX通过。

### N01 更新来源身份和适用性

- 分组／前置：③ 官方通知更新与影响；已有当前事项与旧版规则；新通知为合成资料
- 步骤：触发更新→查看发布单位、范围、年度、批次与版本
- 预期：不是只看标题或搜索摘要；不能将其他年度当现行规则。
- 当前状态：**部分执行**
- 实际结果：从事项概览真实点击查看变更，通知页列发布单位、当前学院/2027届/批次、S04 v1.1及§1截止/§2承诺书，标为合成通知。
- 本轮真实证据：[031 overview-before-notice](evidence/live-browser/031-overview-before-notice.png)、[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)
- 限制／未测部分：仅判该合成来源的界面身份／范围呈现分支；不证明真实网站身份核验或规则适用判断。,通知身份、范围和原文条款标识已见；获取时间及完整身份核验步骤尚未确认，不能把整个N01标通过。

### N02 新旧条款对照

- 分组／前置：③ 官方通知更新与影响；旧版与补充版均可定位
- 步骤：通知提醒→原文对照→影响清单
- 预期：保留两版原文位置、获取时间；条件／任务／日期／材料影响可解释。
- 当前状态：**部分执行**
- 实际结果：通知页并列v1.0/v1.1、09.12/09.10、承诺书及影响；确认后归档保留原文§1/§2和旧版已替代说明。
- 本轮真实证据：[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)、[034 notice-reopen](evidence/live-browser/034-notice-reopen.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)
- 限制／未测部分：未打开完整原文、查看取得时间或验证所有受影响条件／材料映射，不能判完整用例通过。

### N03 调整前的日期提示

- 分组／前置：③ 官方通知更新与影响；变更尚未核对应用
- 步骤：回概览／任务／日历，查看旧截止与新通知日期
- 预期：不只突出旧倒计时；官方来源变化与个人计划是否调整分开。
- 当前状态：**部分执行**
- 实际结果：稍后核对回原概览时，旧09.12/4天与新通知09.10待确认同时醒目可见，旧日期不是唯一指引。
- 本轮真实证据：[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)、[033 notice-later](evidence/live-browser/033-notice-later.png)
- 限制／未测部分：尚未对未调整时的任务、日历全部逐页检查；本次只确认旧概览分支的提醒呈现。

### N04 确认调整与同步

- 分组／前置：③ 官方通知更新与影响；确认新通知适用，尚未改个人计划
- 步骤：查看影响→确认→依次到概览、任务、日历、材料与记录
- 预期：各处日期和版本一致；个人日期独立；新增材料缺项；不覆盖已确认文件。
- 当前状态：**已测不通过**
- 实际结果：确认更新后概览、任务、归档、日历及工作台/重入事项均可显示v1.1和09.10，日历区分个人建议09.09；但从新版归档正常点材料标签进入旧三项清单，无新增承诺书或通知影响标识。
- 本轮真实证据：[034 notice-reopen](evidence/live-browser/034-notice-reopen.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[037 updated-task-filter-completed](evidence/live-browser/037-updated-task-filter-completed.png)、[038 updated-task-filter-uncompleted](evidence/live-browser/038-updated-task-filter-uncompleted.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[040 notice-affected-materials](evidence/live-browser/040-notice-affected-materials.png)、[046 resumed-updated-overview-ready](evidence/live-browser/046-resumed-updated-overview-ready.png)、[047 notice-calendar-verified-click](evidence/live-browser/047-notice-calendar-verified-click.png)、[048 updated-workbench](evidence/live-browser/048-updated-workbench.png)、[049 reenter-updated-item](evidence/live-browser/049-reenter-updated-item.png)
- 限制／未测部分：失败限定于本次已测通知→材料路由，不推断整个文件没有新版材料画板。,041浏览器回退实际回旧计划，042点击未生效，043是旧场景日历，均不能用作更新后日历缺陷证据。,044/045仍加载中；046等待完成后047真实CTA导航才是新版日历证据。

### N05 暂不调整／取消

- 分组／前置：③ 官方通知更新与影响；变更待核对
- 步骤：暂不调整／取消→返回原事项
- 预期：个人计划不静默更改；提醒保留；旧日期不能标成已确认有效。
- 当前状态：**原型分支通过**
- 实际结果：通知页点击“稍后核对”真实返回v1.0概览，保留旧09.12及新09.10待核对提醒；个人计划未以该动作变成已采用新版。
- 本轮真实证据：[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)、[033 notice-later](evidence/live-browser/033-notice-later.png)、[034 notice-reopen](evidence/live-browser/034-notice-reopen.png)
- 限制／未测部分：仅通过“稍后核对”预设分支；不证明真实数据持久化或所有取消控件行为。

### N06 重复通知幂等

- 分组／前置：③ 官方通知更新与影响；同一版本已经处理
- 步骤：再次接收同版本→确认→检查数量与记录
- 预期：不重复建任务、材料或变更记录；可定位原处理记录。
- 当前状态：**未执行**
- 实际结果：未重新接收并确认已处理过的同版本通知。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：一次确认及工作台重入不等于通知幂等测试。

### N07 来源冲突与不可访问

- 分组／前置：③ 官方通知更新与影响；两份适用性不明／矛盾来源；或获取失败
- 步骤：触发→补检索→仍不明→查看结论与其他任务
- 预期：并列保留；待用户核对；最后成功时间可见；只阻塞受影响项。
- 当前状态：**未执行**
- 实际结果：看见待处理中的来源冲突、扫描件和超时卡片，但未打开冲突、补检索或不可访问分支。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：不能仅凭卡片文案判异常处理通过；学生异常补测被自动审批用量上限拒绝，未执行。

### N08 撤销个人安排

- 分组／前置：③ 官方通知更新与影响；更新已影响个人计划
- 步骤：查看撤销范围→确认／取消→再查看来源和日期
- 预期：只恢复个人安排；不改变官方效力，不把旧政策恢复为现行；历史完整。
- 当前状态：**未执行**
- 实际结果：未执行撤销已调整个人安排及其取消分支。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：不能把“稍后核对”当作对已应用更新的撤销。

### X01 个人事项边界与非推免

- 分组／前置：信息边界、规则及异常；本人推免和竞赛两个事项
- 步骤：切换事项→查看任务与材料→尝试个人准备流程
- 预期：无共享、邀请、他人任务分派；非推免不误引推免私有线索。
- 当前状态：**部分执行**
- 实际结果：工作台可见本人与多个事项入口，外校和竞赛卡片明确“仅展示”；本次实际走的是校内推免链路。
- 本轮真实证据：[002 dismiss-cookie](evidence/live-browser/002-dismiss-cookie.png)、[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[048 updated-workbench](evidence/live-browser/048-updated-workbench.png)
- 限制／未测部分：没有切换并完成非推免个人流程；不推断全局不存在团队功能或实际跨事项权限已实现。,新建事项上下文问题另记C01。

### X02 上传截图与官方原文分层

- 分组／前置：信息边界、规则及异常；个人上传通知截图
- 步骤：上传→查看属性→检索找到原文→生成引用
- 预期：截图保持仅本人当前事项；原文单独建立引用，可信度不因改写升级。
- 当前状态：**未执行**
- 实际结果：未上传通知截图，也未从私有线索检索并建立独立官方引用。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：不以后台隐私说明替代三层上传分流测试。

### X03 个人档案跨本人事项复用

- 分组／前置：信息边界、规则及异常；档案已有字段、版本及确认状态
- 步骤：选择复用→核对范围→确认／取消→目标事项
- 预期：只使用本人选择字段；不自动引入其他事项线索；改稿不覆盖档案。
- 当前状态：**未执行**
- 实际结果：未打开个人档案复用选择、范围确认或目标事项。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：未验证跨本人事项复用、取消不写入或改稿不覆盖长期档案。

### X04 自查四态覆盖

- 分组／前置：信息边界、规则及异常；分别准备完整符合、不符合、缺数据和来源冲突样例
- 步骤：逐项生成／展示自查→查看理由与原文
- 预期：严格四态；任务完成、用户确认或机器一致不等于正式资格认定。
- 当前状态：**部分执行**
- 实际结果：排名确认页列出资格四态示例，实际从缺排名到本人确认后显示18/120=15%及符合；仍保留其他待核对项和非正式认定说明。
- 本轮真实证据：[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)
- 限制／未测部分：只走一个符合样例，没有分别执行不符合、缺数据返回和来源冲突的完整四态分支。

### X05 来源状态独立

- 分组／前置：信息边界、规则及异常；官方原文有机器提取状态
- 步骤：查看来源、资格结果、任务状态及义务标签
- 预期：状态分别命名；机器处理不写官方核实。
- 当前状态：**部分执行**
- 实际结果：已查看来源标签、资格结果、任务执行状态与义务文案；排名结果没有写成学校正式认定，后台流程使用自动检查措辞。
- 本轮真实证据：[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)、[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)
- 限制／未测部分：尚未完整检查所有标签与异常分支；“已核对”来源标签的具体确认者未另行验证。

### X06 官方与个人日期

- 分组／前置：信息边界、规则及异常；官方截止有引用，个人有准备日期
- 步骤：改个人日期→查看官方日期→检查相关任务
- 预期：不会改官方规则；无依据日期待核实；时点与适用范围清楚。
- 当前状态：**部分执行**
- 实际结果：候选/已确认任务及更新后日历分别显示建议完成09.09与官方09.10/09.12，官方日期绑定演示通知版本。
- 本轮真实证据：[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[047 notice-calendar-verified-click](evidence/live-browser/047-notice-calendar-verified-click.png)
- 限制／未测部分：未实际修改个人日期并复查官方日期不变；不把静态区分呈现当作修改行为通过。

### X07 停止、失败与重试

- 分组／前置：信息边界、规则及异常；Agent有运行中步骤
- 步骤：停止→查看已完成与未执行→重试
- 预期：范围明确、进度可见；未授权动作不继续，不重复写入。
- 当前状态：**未执行**
- 实际结果：本次没有执行学生端停止与检查点重试。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：后台异常详情说明重试范围不是已执行重试；后续学生异常补测被自动审批用量上限拒绝，未执行。

### X08 高影响确认

- 分组／前置：信息边界、规则及异常；批量状态变更、覆盖已确认档案或删除
- 步骤：打开操作→审阅数量、范围、恢复方式→取消／确认
- 预期：默认不自动执行；取消不写入；不承诺未实现恢复能力。
- 当前状态：**未执行**
- 实际结果：未执行删除、覆盖已确认档案或批量状态变更的影响确认。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：未提供恢复能力的实现证据，不作承诺。

### X09 无对外执行

- 分组／前置：信息边界、规则及异常；需要导师联系或正式提交
- 步骤：查看草稿、入口、状态记录与按钮行为
- 预期：仅供本人审阅、自行办理；无代发／代报名／代提交的授权开关。
- 当前状态：**部分执行**
- 实际结果：材料接受、模拟导出及归档都明确仅内部副本/本人自行办理，未在已测操作中发生对外发送。
- 本轮真实证据：[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[029 material-archive](evidence/live-browser/029-material-archive.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)
- 限制／未测部分：没有完整检查导师联系草稿、外部渠道入口及所有授权开关；不能据此证明全局无外部执行功能或权限控制。

### X10 模型传输同意与最少信息

- 分组／前置：信息边界、规则及异常；若真实实现会调用外部模型
- 步骤：检查服务商、字段、处理说明→拒绝同意→替代流程
- 预期：未同意不上传；外部检索不带私有资料；配置未确定不虚构已实现能力。原型只能验证设计。
- 当前状态：**未执行**
- 实际结果：未执行真实模型传输告知、拒绝同意或替代处理路径。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：本次为静态合成原型，不验证真实请求字段及模型数据处理。

### X11 任务义务四类

- 分组／前置：信息边界、规则及异常；准备四类样例
- 步骤：查看标签、依据→尝试完成与跳过
- 预期：官方必需／官方建议／自主可选／待核实独立于执行状态；建议不伪装硬性要求。
- 当前状态：**已测不通过**
- 实际结果：已确认计划把T07的义务文案写为“Agent建议，非官方义务”，任务汇总也使用“Agent建议”，偏离方案的官方必需/官方建议/自主可选/待核实四类统一枚举。
- 本轮真实证据：[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)
- 限制／未测部分：该文案并未伪装成官方必需；问题为分类一致性。建议用“自主可选（Agent建议）”，不能无依据改成官方建议。,未完整检查全文件四类覆盖或完成/跳过分支，不推断其余类型全局不存在。

### X12 可选事项决策

- 分组／前置：信息边界、规则及异常；自主可选任务待决定
- 步骤：查看成本、理由、跳过影响→采纳／稍后／跳过→返回
- 预期：决定和列表状态一致，不暗中变为官方必需；不承诺录取概率提升。
- 当前状态：**未执行**
- 实际结果：未对自主可选事项执行采纳、稍后决定或跳过。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：接受整个候选计划不等于可选任务三种取舍行为已覆盖。

### X13 本人办理与完成证据

- 分组／前置：信息边界、规则及异常；本人尚未办理
- 步骤：标任务完成／记录自行办理→查看材料和结果
- 预期：来源为本人记录；完成材料不等于已提交，不等于学校接受或资格认定。
- 当前状态：**未执行**
- 实际结果：未标记任务完成或填写本人已办理记录。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：已见本人自行提交边界与任务状态，但不代替实际办理记录行为测试。

### X14 归档与复用

- 分组／前置：信息边界、规则及异常；事项已归档合成版本
- 步骤：查看快照→选目标事项复用→取消／确认
- 预期：材料、规则、事实和确认版本可追溯；仅本人，不公开不送审。
- 当前状态：**部分执行**
- 实际结果：进入材料归档和通知归档，看到材料v2、原稿v1、F02/S02及确认/接受/模拟导出记录；明确不等于外部提交。
- 本轮真实证据：[029 material-archive](evidence/live-browser/029-material-archive.png)、[030 return-confirmed-materials](evidence/live-browser/030-return-confirmed-materials.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)
- 限制／未测部分：未选择目标事项复用、执行取消/确认或验证跨事项范围，因此不能判完整用例通过。

### B01 官方来源处理流程

- 分组／前置：后台必要模块；后台来源模块可访问
- 步骤：查看获取、提取、自动检查、缓存与异常状态
- 预期：无人工审核发布官方政策流程；状态不标官方核实。
- 当前状态：**原型分支通过**
- 实际结果：从后台运行概览真实点击知识与规则，当前Page2可见按事项检索官方来源→提取条款→自动检查→保留来源及异常记录，说明不以前置人工审核发布；列表状态为已检查/有异常等。
- 本轮真实证据：[050 admin-entry](evidence/live-browser/050-admin-entry.png)、[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)
- 限制／未测部分：仅判已观察来源治理页面分支的设计表达，不证明实际自动获取、缓存、检查算法或所有隐藏配置。

### B02 来源与私有资料隔离

- 分组／前置：后台必要模块；有公共来源和个人上传线索
- 步骤：查看后台详情／导入／搜索范围
- 预期：不把私有截图转公开，不展示真实用户材料正文。权限真实实现另测。
- 当前状态：**部分执行**
- 实际结果：已查看来源列表和脱敏异常详情，详情明确个人截图/材料留在本人工作区，后台不展示正文；已测画面未显示私人正文。
- 本轮真实证据：[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)、[054 admin-agent-runs](evidence/live-browser/054-admin-agent-runs.png)、[055 admin-exception-detail](evidence/live-browser/055-admin-exception-detail.png)
- 限制／未测部分：未执行导入、搜索或私有截图处理，无法证明权限隔离、数据泄露防护或全局资料范围。

### B03 模板详情及版本

- 分组／前置：后台必要模块；至少推免与一个非推免模板
- 步骤：模板→阶段／字段／范围／引用→版本比较
- 预期：模板配置与官方证据分开，默认阶段不冒充适用政策。
- 当前状态：**部分执行**
- 实际结果：已进入知识与规则页查看可见来源列表，未在已达界面发现明确模板入口。
- 本轮真实证据：[050 admin-entry](evidence/live-browser/050-admin-entry.png)、[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)
- 限制／未测部分：未完整遍历文件/全部入口，不能确认模板模块不存在；模板阶段/字段/版本比较未执行。

### B04 模板更新／启停影响

- 分组／前置：后台必要模块；模板已有工作区使用
- 步骤：查看影响→确认／取消→已有事项
- 预期：不改变政策效力；不静默批量改个人计划；迁移建议需本人确认。
- 当前状态：**未执行**
- 实际结果：未进入模板启停/更新影响预览，也未确认或取消配置变更。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：没有证据判定已有事项迁移或模板启停能力。

### B05 执行详情与技术重试

- 分组／前置：后台必要模块；Agent有失败执行记录
- 步骤：查看授权、步骤、版本、原因→重试／停止
- 预期：技术重试幂等；政策疑点提示当前用户，不由管理员裁决。
- 当前状态：**部分执行**
- 实际结果：从Agent任务列表真实打开AG-1048异常详情，可见第2/4步超时、1/4检查点、错误原因、脱敏元数据及重试范围；通过返回按钮回到列表。
- 本轮真实证据：[054 admin-agent-runs](evidence/live-browser/054-admin-agent-runs.png)、[055 admin-exception-detail](evidence/live-browser/055-admin-exception-detail.png)、[067 responsive-admin-return-list](evidence/live-browser/067-responsive-admin-return-list.png)
- 限制／未测部分：未实际点击技术重试或停止；不能将详情文字等同幂等重试已通过。

### B06 日志与管理权限

- 分组／前置：后台必要模块；后台日志可查看／导出
- 步骤：查看最少字段→详情／导出→用户端入口
- 预期：无私有正文、完整对话和敏感资料；不冒用用户，不替用户确认资格或接受改稿。
- 当前状态：**部分执行**
- 实际结果：已查看AG-1048脱敏详情，画面限定任务编号、状态、失败步骤和错误元数据，明确不访问私人正文。
- 本轮真实证据：[054 admin-agent-runs](evidence/live-browser/054-admin-agent-runs.png)、[055 admin-exception-detail](evidence/live-browser/055-admin-exception-detail.png)
- 限制／未测部分：没有执行日志导出/打开用户端或验证管理权限；静态脱敏样例不证明真实安全隔离。

### U01 所有关键热点与返回

- 分组／前置：UI、导航与桌面体验；取得Page2原型起点
- 步骤：依次操作菜单、按钮、父级热点、组件、覆盖层与返回
- 预期：目标位于当前版本、事项正确；无死路或遮挡；不能只检查文字节点reaction。
- 当前状态：**已测不通过**
- 实际结果：多条真实业务热点成功导航，否定此前TinyFish“全局静态无热点”推断；但当前知识与规则首行“查看记录”文字及箭头分别精确点击后URL与截图均未变化，缺少可见反馈。
- 本轮真实证据：[002 dismiss-cookie](evidence/live-browser/002-dismiss-cookie.png)、[003 new-workspace](evidence/live-browser/003-new-workspace.png)、[007 create-filled](evidence/live-browser/007-create-filled.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)、[018 agent-conversation](evidence/live-browser/018-agent-conversation.png)、[021 send-request-correct](evidence/live-browser/021-send-request-correct.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[025 reject-material-suggestion](evidence/live-browser/025-reject-material-suggestion.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[050 admin-entry](evidence/live-browser/050-admin-entry.png)、[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)、[052 admin-source-record](evidence/live-browser/052-admin-source-record.png)、[053 admin-source-record-arrow](evidence/live-browser/053-admin-source-record-arrow.png)、[054 admin-agent-runs](evidence/live-browser/054-admin-agent-runs.png)、[055 admin-exception-detail](evidence/live-browser/055-admin-exception-detail.png)
- 限制／未测部分：故障仅限定已点击的首行查看记录入口；不据此断言没有reaction或所有后台详情失效。,051/052/053截图SHA-256相同；未完成全局全部热点、组件、覆盖层与变量审查。

### U02 布局组件与信息层次

- 分组／前置：UI、导航与桌面体验；有实际画面
- 步骤：比较标题、主次按钮、表单、弹窗、卡片、标签、错误和空状态
- 预期：含义一致、主操作明确、文字可理解；基于截图记录具体问题而非笼统说不美观。
- 当前状态：**部分执行**
- 实际结果：已在真实截图比较紫色品牌、导航、主次按钮、必填错误、确认/拒绝/成功和文字状态，主要页面可读，发现的具体交互问题另行记录。
- 本轮真实证据：[003 new-workspace](evidence/live-browser/003-new-workspace.png)、[004 create-empty-validation](evidence/live-browser/004-create-empty-validation.png)、[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)、[022 supplement-role](evidence/live-browser/022-supplement-role.png)、[024 add-draft-to-review](evidence/live-browser/024-add-draft-to-review.png)、[025 reject-material-suggestion](evidence/live-browser/025-reject-material-suggestion.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[032 view-notice-change](evidence/live-browser/032-view-notice-change.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[051 admin-official-sources](evidence/live-browser/051-admin-official-sources.png)、[055 admin-exception-detail](evidence/live-browser/055-admin-exception-detail.png)
- 限制／未测部分：未做完整组件一致性/对比度测量/键盘或弹窗矩阵，不笼统宣称UI全部通过。

### U03 桌面视口与长内容

- 分组／前置：UI、导航与桌面体验；可调整预览视口或真实前端窗口
- 步骤：在1280／1440／1920宽度检查概览、任务、差异、后台表格
- 预期：侧栏与卡片合理重排；按钮可达；表格局部滚动；整页缩小不计响应式通过。
- 当前状态：**已测不通过**
- 实际结果：在查看器实际选择Responsive并确认URL content-scaling=responsive后，对后台异常详情和列表执行1280/1440/1920真实视口检查。1280列表操作列不可见，经本次横纵滚动仍未恢复；同节点1440/1920可见查看异常/详情。
- 本轮真实证据：[060 admin-1280-initial-mode](evidence/live-browser/060-admin-1280-initial-mode.png)、[062 open-options-fast](evidence/live-browser/062-open-options-fast.png)、[063 enable-responsive-mode](evidence/live-browser/063-enable-responsive-mode.png)、[064 admin-responsive-1440](evidence/live-browser/064-admin-responsive-1440.png)、[065 admin-responsive-1920](evidence/live-browser/065-admin-responsive-1920.png)、[066 admin-responsive-1280](evidence/live-browser/066-admin-responsive-1280.png)、[067 responsive-admin-return-list](evidence/live-browser/067-responsive-admin-return-list.png)、[068 focus-admin-table](evidence/live-browser/068-focus-admin-table.png)、[069 admin-table-horizontal-scroll](evidence/live-browser/069-admin-table-horizontal-scroll.png)、[070 admin-table-bottom](evidence/live-browser/070-admin-table-bottom.png)、[071 reset-admin-table-scroll](evidence/live-browser/071-reset-admin-table-scroll.png)、[072 admin-table-responsive-1440](evidence/live-browser/072-admin-table-responsive-1440.png)、[073 admin-table-responsive-1920](evidence/live-browser/073-admin-table-responsive-1920.png)、[074 prepare-diff-1440](evidence/live-browser/074-prepare-diff-1440.png)、[075 resume-diff-responsive](evidence/live-browser/075-resume-diff-responsive.png)
- 限制／未测部分：判定限定已测后台列表1280操作可达性；不推断所有页面没有响应式。,材料差异页仅补到1440直达截图075；下一批1280/1920操作被自动审批用量上限拒绝，未执行。,Actual size截图与Responsive截图分开；062菜单/063选择及URL为模式证据。

### U04 缩放、焦点和非颜色提示

- 分组／前置：UI、导航与桌面体验；支持对应实际预览或实现环境
- 步骤：200%缩放→键盘焦点与Tab→检查标签和错误
- 预期：不遮挡关键动作；状态有文字，不只靠颜色；原型不支持的行为记待验证。
- 当前状态：**未执行**
- 实际结果：未执行200%浏览器缩放、Tab焦点遍历或完整非颜色提示用例。
- 本轮真实证据：无本轮业务点击证据；不能用文档或别处结果态代替。
- 限制／未测部分：Responsive视口变化不是200%缩放；已见文字状态不能替代键盘与缩放验证。

### U05 场景状态与重置

- 分组／前置：UI、导航与桌面体验；三条场景已配置
- 步骤：从确认后返回、跨页→查看状态→显式重置
- 预期：不暗中丢失确认／更新状态；预设跳转与重置明确，不冒充持久化。
- 当前状态：**已测不通过**
- 实际结果：排名页确认18/120后正常切换Agent待处理又显示排名/证明待补，计划确认后T02仍待补，未解释数据已确认但证明仍待补的区别；新建示例也进入既有上下文。材料分支归档后返回保持v2、通知分支日历/工作台重入保持v1.1的子路径则正常。
- 本轮真实证据：[008 enter-new-item](evidence/live-browser/008-enter-new-item.png)、[009 new-item-source](evidence/live-browser/009-new-item-source.png)、[010 rank-ask](evidence/live-browser/010-rank-ask.png)、[011 rank-confirm](evidence/live-browser/011-rank-confirm.png)、[012 agent-pending](evidence/live-browser/012-agent-pending.png)、[013 review-candidate-plan](evidence/live-browser/013-review-candidate-plan.png)、[014 plan-decline](evidence/live-browser/014-plan-decline.png)、[016 plan-confirm](evidence/live-browser/016-plan-confirm.png)、[027 accept-material-suggestion](evidence/live-browser/027-accept-material-suggestion.png)、[028 export-copy](evidence/live-browser/028-export-copy.png)、[029 material-archive](evidence/live-browser/029-material-archive.png)、[030 return-confirmed-materials](evidence/live-browser/030-return-confirmed-materials.png)、[035 notice-confirm-update](evidence/live-browser/035-notice-confirm-update.png)、[036 notice-affected-tasks](evidence/live-browser/036-notice-affected-tasks.png)、[039 notice-update-archive](evidence/live-browser/039-notice-update-archive.png)、[040 notice-affected-materials](evidence/live-browser/040-notice-affected-materials.png)、[047 notice-calendar-verified-click](evidence/live-browser/047-notice-calendar-verified-click.png)、[048 updated-workbench](evidence/live-browser/048-updated-workbench.png)、[049 reenter-updated-item](evidence/live-browser/049-reenter-updated-item.png)
- 限制／未测部分：失败为原型跨页状态表达/上下文不一致，不推断真实后端保存失败。,通知5+T08与计划5+T06/T07在画面中明确标为独立预设分支，不能据6/7数量差再报合并缺陷。,041-043浏览器回退路线、044-045加载中点击不作为本项业务失败证据；显式重置未全面检查。

## 重测入口

RT-01～07见[问题清单](issue-log.md)。原用例JSON附有前次结果和最新证据序号，见[用例索引](evidence/test-case-index.json)。完整动作坐标和URL见[actions.jsonl](evidence/live-browser/actions.jsonl)，逐图范围说明见[证据审计](evidence/live-browser/README.md)。
