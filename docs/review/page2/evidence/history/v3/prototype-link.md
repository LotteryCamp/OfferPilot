# Page2 地址、节点与访问复核

> v3最新状态：TinyFish已显示原始Present并完成初检运行；2条局部尝试受阻、2条局部观察待核验、51条未执行，完整通过0。当前等待用户保存Figma登录后复测。详见文件末尾v3补充及evidence/tinyfish/runtime-audit.md。


> 2026-11-09／v2 导出材料复核版（Asia/Shanghai）。目标：Page2，导出说明写作“Page 2”。
> Codex 辅助完成离线文档走查与基础图片检查；不代替陈常群、张锦昊署名或宣称已手工点击。
> 原型只读；未修改Figma；未进行Git提交或推送。

## 本次已获得的定位

本轮取得的是作者导出说明中的 **Page 2**（用户称Page2），不再将旧0:1作为最新起点。

- [学生端Present入口](https://www.figma.com/proto/VY1sWwkYE55AESpwZwter6?page-id=314%3A90&node-id=314-91&starting-point-node-id=314%3A91)：作者提供页面314:90、起点314:91，原文L9。
- [后台Present入口](https://www.figma.com/proto/VY1sWwkYE55AESpwZwter6?page-id=314%3A90&node-id=314-1673&starting-point-node-id=314%3A1673)：作者提供页面314:90、起点314:1673，原文L10。
- [Page 2设计页面](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-90)：作者提供，原文L11。
- [接线索引画板](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=332-31136)：作者提供，原文L152；本包没有该画板图片或连线数据。

**以上链接文本已从说明中提取，但在线访问和节点归属尚未独立验证。** 完整12项定位见 [节点索引](evidence/page2-node-index.md)。

## 已执行的材料检查

【v2离线阶段历史记录】已实际读取本次 `prototyping.zip`：1份 `prototype.md` 与13张PNG。说明第13行明确配图来自 **Page 1**，因此这些图片只能作为旧版基础布局和历史问题的参考。Page2的入口、状态名称与节点是作者在说明中提供的定位，未经过本轮在线读取确认。第7行“已完成Present点击自测”是作者自述，不是本轮独立复测结果。再次读取确切Page2节点314:90仍被额度限制拦截。本轮已完成三条路线的文档走查，没有完成真实点击、原生动作检查或窗口缩放。

- `prototyping.zip`：1915296字节；SHA-256 `03291577092F5FA41D7F140CDD7C1F9FEAB391DDA15D89555694259254BBBAA8`。
- `prototype.md`：162行；SHA-256 `B831576DF444D8088A9704268E7846E5DD8FE1EA34D765A723AC79ED72EF0E16`。
- 图片：13张PNG；原始字节、尺寸和哈希见 [导出清单](evidence/export-manifest.json)。
- 源说明和图片保存在 [evidence/source-export/prototyping/](evidence/source-export/prototyping/prototype.md)，未把旧图重命名为Page2证据。
- 第7行的自测声明没有独立测试日志、执行日期、执行人签名或运行录像；仅记作者报告。

## 在线访问记录

|顺序|操作|结果|
|---|---|---|
|A01–A05|此前创建会话、读目录、账号诊断、备用网页和元数据读取|会话成功但页面读取受额度限制；学生Full诊断与Starter错误文案有差异，原因未明|
|A06|本轮按作者精确页面节点314:90读取元数据|再次返回同类额度限制；没有取得最新页面、截图或原型动作|

见 [脱敏访问记录](evidence/access-attempts.json)。本轮未尝试修改文件、共享、套餐或计费设置。调用限制不归为产品缺陷。

## 需求基线

正式方案SHA-256 `C8AE7BE0C5EE9C9C32AD30AEFECFA68B84D6832333958991CE8ADA28E9D5B9EE`；章节定位见 [requirements-baseline.md](evidence/requirements-baseline.md)。导出说明与方案有冲突时，先记录差异并请团队核对，不能无依据把说明中的计划当作已实现事实。

## 复测条件

取得Page2关键状态PNG／PDF、接线索引或原型动作导出，可进一步核对设计与配置；完整点击、视口和真实文件检查仍需可运行的Present或实现环境。优先使用上列精确入口，不再误入Page1或旧交互修订页。具体用例见 [interaction-test-cases.md](interaction-test-cases.md)。

## 2026-11-09 15:59 读取恢复复查

再次通过Figma插件读取确切Page2节点314:90，仍返回MCP调用额度限制，未取得页面数据。随后重新诊断，账号仍显示学生套餐、Full席位；错误文案仍称Starter，原因未明。未继续重复请求截图或交互，未进行Present点击、窗口缩放或设计修改。

本次只更新访问记录；55条运行用例仍未执行，既有文档走查和旧图证据边界不变。A07／A08的记录时间为上海时间，见evidence/access-attempts.json。


## v3 TinyFish浏览器初检补充（2026-11-09）

2026-11-09 新增 TinyFish 浏览器初检：原始 Page2 Present 已在浏览器中显示，MCP 读取恢复与否不因此改变。已完成5次浏览器运行（访问试验、创建、材料、通知、后台／视口），但未完整走通三条主线，也没有可下载的新截图。业务入口点击未推进、登录弹窗及运行记录内部矛盾仍待复测。55条用例中2条为局部尝试受阻、2条为局部画面观察待核验、51条未执行；完整验收通过0，确认产品失败0。登录环境已由用户同意配置，等待用户自行登录并保存后继续。

MCP此前仍受限，但TinyFish已实际显示原始Present。浏览器匿名访问可显示部分画面，之后部分运行出现登录遮挡；用户已同意设置登录状态。配置读取和运行测试是不同路径，不能把浏览器访问成功写成MCP额度已恢复。

详见 [运行审计](evidence/tinyfish/runtime-audit.md)；真实截图仍未取得，运行日志不能冒称截图。
