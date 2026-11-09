# Page 2 真实浏览器复测证据说明

> 2026-11-09（Asia/Shanghai）／v4 真实浏览器复测
> 本轮只读访问原始 Page 2，未修改 Figma、未发送消息、未提交 Git。浏览器中的合成演示不等于真实数据处理、真实 DOCX 导出或上线功能验收。
> 本文最新结论以本轮真实PNG、坐标动作及URL记录为准。旧版“等待登录／55条未执行／确认缺陷0”等是历史状态，不再作为当前结论。


## 方法和证据边界

- 以本机独立Chrome无头会话进入原始Present，按真实截图确定坐标，逐步点击产品热点并记录URL和PNG。本机会话没有复制用户浏览器cookie；无需登录墙即可读取本次所测公开Present，但不能推断所有文件或后台均公开可访问。
- 真实证据共75张PNG，包含加载中、纠正坐标和查看器设置等过程图；不能把75张当75个用例通过。PNG未经裁剪、拼接或重画。
- 学生主线采用页面内业务入口；没有使用Figma查看器Next/Previous代替业务跳转。UI显示的Next控件未被用于这些本地业务路径。浏览器AltLeft(041)与深链恢复(044)均单独列出。
- 读取了浏览器实际标题“OfferPilot - Page 2”及节点URL；没有读取Figma原生Prototype面板reaction定义、组件状态配置或Auto Layout参数。实点证实的跳转不等于全文件原生动作审计已完成。
- 截图及动作UTC时间见原始记录（本地日期同为2026-11-09）；本轮视口为1440×1000，另有1280×900及1920×1080。062实际菜单显示初始为Actual size；063选择Responsive后URL为content-scaling=responsive。后台宽度结论仅据其后截图。
- 076之后的材料多宽度／学生异常批次因自动审批服务用量上限未被执行，无对应截图。不使用别的浏览器工具绕过该阻碍。

## 三条场景的实际结果

|场景|实际证据顺序|结论|
|---|---|---|
|① 首次创建推免申请工作区|003→004→006→007→008→009→010→011→012→013→014→015→016|已走到创建成功、排名确认、计划拒绝及确认结果；新建事项身份与后续已有任务不连续，排名确认在后续待办中倒退。首次主线不通过；任意输入、失败重试、无来源建项尚未测。|
|② 个人材料审阅与版本|017→018→019→021→022→023→024→025→026→027→028→029→030|追问、事实确认、更新草稿、左右对照、拒绝重审、接受、模拟DOCX、归档和回写作台均真实可达。导出前二次事实核对缺口未通过；历史恢复及真实DOCX仍未执行。|
|③ 官方通知变化|031→032→033→034→035→036→037→038→039→040；046→047→048→049|稍后保留v1.0并同时提醒v1.1；确认后概览、任务、归档、新版日历、工作台及重入均有真实证据。039→040材料入口回旧清单，材料影响未通过。046是深链恢复后另段实点，不伪称一段不中断路径。|

## 确认与排除

本轮实测确认4项P1、3项P2具体问题，结论见本页三条场景结果。不宣称真实数据泄露、后端状态失效、实际原件被覆盖或全站没有连线。

- 005、020分别点击了上一状态的坐标，随后006、021修正并成功；不能记为按钮故障。
- 041浏览器返回实际回到332:29006；042点击无效、043进入旧日历。它们不能用于证明新版日历错误。
- 044/045是加载中画面；046才恢复显示新版概览，047后才是有效日历点击。
- 035/036明确通知演示使用原5项+T08=6，不合并计划P1.1的T06/T07；此预设范围已明示，不作为任务计数缺陷。
- 060为Actual size下裁切，不作为响应式失败证据。067/070才是Responsive后台任务表1280操作列问题。
- 075仅是1440材料对照状态的Responsive截图；未取得该材料页1280、1920响应式证据。也未做200%缩放、键盘焦点或对比度比值测试。
- 原导出13张PNG仍为Page1；本轮原始Present截图单独存放，不改旧图标签冒充Page2。

## 本轮动作与截图索引

|序号|动作|返回节点|视口|截图|说明|
|---|---|---|---|---|---|
|1|workbench|314-91|1440×1000|[001 workbench](001-workbench.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|2|dismiss-cookie|314-91|1440×1000|[002 dismiss-cookie](002-dismiss-cookie.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|3|new-workspace|314-181|1440×1000|[003 new-workspace](003-new-workspace.png)|真实过程记录；非单独用例通过|
|4|create-empty-validation|332-28338|1440×1000|[004 create-empty-validation](004-create-empty-validation.png)|真实过程记录；非单独用例通过|
|5|fill-example|332-28338|1440×1000|[005 fill-example](005-fill-example.png)|未命中当前业务控件或加载中，排除功能定性|
|6|fill-example-correct|332-28425|1440×1000|[006 fill-example-correct](006-fill-example-correct.png)|真实过程记录；非单独用例通过|
|7|create-filled|332-28515|1440×1000|[007 create-filled](007-create-filled.png)|真实过程记录；非单独用例通过|
|8|enter-new-item|332-28627|1440×1000|[008 enter-new-item](008-enter-new-item.png)|真实过程记录；非单独用例通过|
|9|new-item-source|314-613|1440×1000|[009 new-item-source](009-new-item-source.png)|真实过程记录；非单独用例通过|
|10|rank-ask|332-28756|1440×1000|[010 rank-ask](010-rank-ask.png)|真实过程记录；非单独用例通过|
|11|rank-confirm|332-28873|1440×1000|[011 rank-confirm](011-rank-confirm.png)|真实过程记录；非单独用例通过|
|12|agent-pending|314-1395|1440×1000|[012 agent-pending](012-agent-pending.png)|真实过程记录；非单独用例通过|
|13|review-candidate-plan|314-713|1440×1000|[013 review-candidate-plan](013-review-candidate-plan.png)|真实过程记录；非单独用例通过|
|14|plan-decline|314-810|1440×1000|[014 plan-decline](014-plan-decline.png)|真实过程记录；非单独用例通过|
|15|plan-reopen|314-713|1440×1000|[015 plan-reopen](015-plan-reopen.png)|真实过程记录；非单独用例通过|
|16|plan-confirm|332-29006|1440×1000|[016 plan-confirm](016-plan-confirm.png)|真实过程记录；非单独用例通过|
|17|materials-workbench|314-1098|1440×1000|[017 materials-workbench](017-materials-workbench.png)|真实过程记录；非单独用例通过|
|18|agent-conversation|314-1204|1440×1000|[018 agent-conversation](018-agent-conversation.png)|真实过程记录；非单独用例通过|
|19|choose-personal-statement|332-29159|1440×1000|[019 choose-personal-statement](019-choose-personal-statement.png)|真实过程记录；非单独用例通过|
|20|send-demo-request|332-29159|1440×1000|[020 send-demo-request](020-send-demo-request.png)|未命中当前业务控件或加载中，排除功能定性|
|21|send-request-correct|314-1332|1440×1000|[021 send-request-correct](021-send-request-correct.png)|真实过程记录；非单独用例通过|
|22|supplement-role|332-29258|1440×1000|[022 supplement-role](022-supplement-role.png)|真实过程记录；非单独用例通过|
|23|confirm-role-update-draft|332-29360|1440×1000|[023 confirm-role-update-draft](023-confirm-role-update-draft.png)|真实过程记录；非单独用例通过|
|24|add-draft-to-review|332-29464|1440×1000|[024 add-draft-to-review](024-add-draft-to-review.png)|真实过程记录；非单独用例通过|
|25|reject-material-suggestion|332-29717|1440×1000|[025 reject-material-suggestion](025-reject-material-suggestion.png)|真实过程记录；非单独用例通过|
|26|material-review-again|332-29464|1440×1000|[026 material-review-again](026-material-review-again.png)|真实过程记录；非单独用例通过|
|27|accept-material-suggestion|332-29594|1440×1000|[027 accept-material-suggestion](027-accept-material-suggestion.png)|真实过程记录；非单独用例通过|
|28|export-copy|332-29838|1440×1000|[028 export-copy](028-export-copy.png)|真实过程记录；非单独用例通过|
|29|material-archive|332-29941|1440×1000|[029 material-archive](029-material-archive.png)|真实过程记录；非单独用例通过|
|30|return-confirmed-materials|351-679|1440×1000|[030 return-confirmed-materials](030-return-confirmed-materials.png)|真实过程记录；非单独用例通过|
|31|overview-before-notice|314-453|1440×1000|[031 overview-before-notice](031-overview-before-notice.png)|真实过程记录；非单独用例通过|
|32|view-notice-change|314-1576|1440×1000|[032 view-notice-change](032-view-notice-change.png)|真实过程记录；非单独用例通过|
|33|notice-later|314-453|1440×1000|[033 notice-later](033-notice-later.png)|真实过程记录；非单独用例通过|
|34|notice-reopen|314-1576|1440×1000|[034 notice-reopen](034-notice-reopen.png)|真实过程记录；非单独用例通过|
|35|notice-confirm-update|332-30544|1440×1000|[035 notice-confirm-update](035-notice-confirm-update.png)|真实过程记录；非单独用例通过|
|36|notice-affected-tasks|332-30692|1440×1000|[036 notice-affected-tasks](036-notice-affected-tasks.png)|真实过程记录；非单独用例通过|
|37|updated-task-filter-completed|352-598|1440×1000|[037 updated-task-filter-completed](037-updated-task-filter-completed.png)|真实过程记录；非单独用例通过|
|38|updated-task-filter-uncompleted|352-749|1440×1000|[038 updated-task-filter-uncompleted](038-updated-task-filter-uncompleted.png)|真实过程记录；非单独用例通过|
|39|notice-update-archive|332-30844|1440×1000|[039 notice-update-archive](039-notice-update-archive.png)|真实过程记录；非单独用例通过|
|40|notice-affected-materials|314-1098|1440×1000|[040 notice-affected-materials](040-notice-affected-materials.png)|真实过程记录；非单独用例通过|
|41|browser-back-to-updated-archive|332-29006|1440×1000|[041 browser-back-to-updated-archive](041-browser-back-to-updated-archive.png)|浏览器回退到计划状态，非通知归档|
|42|updated-overview-from-archive|332-29006|1440×1000|[042 updated-overview-from-archive](042-updated-overview-from-archive.png)|未命中当前业务控件或加载中，排除功能定性|
|43|updated-calendar|314-252|1440×1000|[043 updated-calendar](043-updated-calendar.png)|从旧计划进入旧日历，不用于新版同步定性|
|44|resume-notice-updated-state|332-30544|1440×1000|[044 resume-notice-updated-state](044-resume-notice-updated-state.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|45|notice-calendar-cta|332-30544|1440×1000|[045 notice-calendar-cta](045-notice-calendar-cta.png)|未命中当前业务控件或加载中，排除功能定性|
|46|resumed-updated-overview-ready|332-30544|1440×1000|[046 resumed-updated-overview-ready](046-resumed-updated-overview-ready.png)|真实过程记录；非单独用例通过|
|47|notice-calendar-verified-click|332-30969|1440×1000|[047 notice-calendar-verified-click](047-notice-calendar-verified-click.png)|真实过程记录；非单独用例通过|
|48|updated-workbench|351-1078|1440×1000|[048 updated-workbench](048-updated-workbench.png)|真实过程记录；非单独用例通过|
|49|reenter-updated-item|332-30544|1440×1000|[049 reenter-updated-item](049-reenter-updated-item.png)|真实过程记录；非单独用例通过|
|50|admin-entry|314-1673|1440×1000|[050 admin-entry](050-admin-entry.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|51|admin-official-sources|314-2100|1440×1000|[051 admin-official-sources](051-admin-official-sources.png)|真实过程记录；非单独用例通过|
|52|admin-source-record|314-2100|1440×1000|[052 admin-source-record](052-admin-source-record.png)|真实过程记录；非单独用例通过|
|53|admin-source-record-arrow|314-2100|1440×1000|[053 admin-source-record-arrow](053-admin-source-record-arrow.png)|真实过程记录；非单独用例通过|
|54|admin-agent-runs|314-2452|1440×1000|[054 admin-agent-runs](054-admin-agent-runs.png)|真实过程记录；非单独用例通过|
|55|admin-exception-detail|332-30438|1440×1000|[055 admin-exception-detail](055-admin-exception-detail.png)|真实过程记录；非单独用例通过|
|56|viewer-controls|332-30438|1440×1000|[056 viewer-controls](056-viewer-controls.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|57|show-viewer-ui|332-30438|1440×1000|[057 show-viewer-ui](057-show-viewer-ui.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|58|viewer-options|332-30438|1440×1000|[058 viewer-options](058-viewer-options.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|59|viewer-option-text|332-30438|1440×1000|[059 viewer-option-text](059-viewer-option-text.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|60|admin-1280-initial-mode|332-30438|1280×900|[060 admin-1280-initial-mode](060-admin-1280-initial-mode.png)|真实过程记录；非单独用例通过|
|61|reveal-options|332-30438|1280×900|[061 reveal-options](061-reveal-options.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|62|open-options-fast|332-30438|1280×900|[062 open-options-fast](062-open-options-fast.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|63|enable-responsive-mode|332-30438|1280×900|[063 enable-responsive-mode](063-enable-responsive-mode.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|64|admin-responsive-1440|332-30438|1440×1000|[064 admin-responsive-1440](064-admin-responsive-1440.png)|真实过程记录；非单独用例通过|
|65|admin-responsive-1920|332-30438|1920×1080|[065 admin-responsive-1920](065-admin-responsive-1920.png)|真实过程记录；非单独用例通过|
|66|admin-responsive-1280|332-30438|1280×900|[066 admin-responsive-1280](066-admin-responsive-1280.png)|真实过程记录；非单独用例通过|
|67|responsive-admin-return-list|314-2452|1280×900|[067 responsive-admin-return-list](067-responsive-admin-return-list.png)|真实过程记录；非单独用例通过|
|68|focus-admin-table|314-2452|1280×900|[068 focus-admin-table](068-focus-admin-table.png)|真实过程记录；非单独用例通过|
|69|admin-table-horizontal-scroll|314-2452|1280×900|[069 admin-table-horizontal-scroll](069-admin-table-horizontal-scroll.png)|真实过程记录；非单独用例通过|
|70|admin-table-bottom|314-2452|1280×900|[070 admin-table-bottom](070-admin-table-bottom.png)|真实过程记录；非单独用例通过|
|71|reset-admin-table-scroll|314-2452|1280×900|[071 reset-admin-table-scroll](071-reset-admin-table-scroll.png)|真实过程记录；非单独用例通过|
|72|admin-table-responsive-1440|314-2452|1440×1000|[072 admin-table-responsive-1440](072-admin-table-responsive-1440.png)|真实过程记录；非单独用例通过|
|73|admin-table-responsive-1920|314-2452|1920×1080|[073 admin-table-responsive-1920](073-admin-table-responsive-1920.png)|真实过程记录；非单独用例通过|
|74|prepare-diff-1440|314-2452|1440×1000|[074 prepare-diff-1440](074-prepare-diff-1440.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
|75|resume-diff-responsive|332-29464|1440×1000|[075 resume-diff-responsive](075-resume-diff-responsive.png)|入口／加载／设置／定位记录，不能代替业务点击通过|
