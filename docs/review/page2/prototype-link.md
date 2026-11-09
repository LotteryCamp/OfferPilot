# Page 2 原型链接与访问复测记录（v4）

> 2026-11-09（Asia/Shanghai）／v4 真实浏览器复测
> 本轮只读访问原始 Page 2，未修改 Figma、未发送消息、未提交 Git。浏览器中的合成演示不等于真实数据处理、真实 DOCX 导出或上线功能验收。
> 本文最新结论以本轮真实PNG、坐标动作及URL记录为准。旧版“等待登录／55条未执行／确认缺陷0”等是历史状态，不再作为当前结论。


- [原始设计文件／Page2页面](https://www.figma.com/design/VY1sWwkYE55AESpwZwter6/OfferPilot?node-id=314-90)
- [学生端Present入口](https://www.figma.com/proto/VY1sWwkYE55AESpwZwter6/OfferPilot?page-id=314%3A90&node-id=314-91&starting-point-node-id=314%3A91)
- [后台Present入口](https://www.figma.com/proto/VY1sWwkYE55AESpwZwter6/OfferPilot?page-id=314%3A90&node-id=314-1673&starting-point-node-id=314%3A1673)

## 实际访问结果

本轮用户已保存Figma登录状态；TinyFish以保存profile运行，入口未再次出现登录遮挡，但画布精准定位仍受限。独立Chrome随后真实打开原始Present，标题为“OfferPilot - Page 2”，业务热点能够触发导航，75张PNG和动作URL已保存。这足以否定TinyFish此前“所有页面都只是静态无连接”的笼统推断。

这条浏览器路径没有恢复Figma MCP额度，也没有读到Prototype面板动作配置。未修改原设计。当前不能保证设计文件编辑器、每个深链或用户私有后台均可免登录。

## 时间、节点与配置证据

- 第一张真实截图UTC 2026-11-09T09:18:44.960Z；最后一张UTC 2026-11-09T09:54:37.578Z（对应本地2026-11-09）。
- Page2页314:90；所测节点来自浏览器运行URL，完整[节点／动作／截图索引](evidence/live-browser/README.md)。作者原索引保留在[evidence/page2-node-index.md](evidence/page2-node-index.md)。
- 062选项菜单显示初始Actual size；063选择Responsive后记录scaling=contain及content-scaling=responsive。1280、1440、1920测试采用该模式；不能以Fit width截图冒充适配。
- 041浏览器回退及044深链恢复已经单列；它们不替代场景内业务跳转。
- 下一批材料多宽度和学生端异常恢复在自动审批服务达到用量上限时未被执行；不用重登解决该限制。

## 后续复测前检查

1. 确认标题仍是Page 2，起点及节点正确，记录修改日期；如果原型已更新，先记录新节点映射。
2. 每条业务路线从产品按钮进入，保存前后截图及URL；不可用查看器Next冒充。
3. 配置级审查需另行只读获取原生reaction、滚动和Auto Layout信息；本轮不虚填已读取。
4. 请勿在提交包放cookies、密码、登录设置URL或个人账户资料。本包没有这些内容。

历史访问阻碍与TinyFish辅助观察保留在[历史v3](evidence/history/v3/prototype-link.md)与[原日志审计](evidence/tinyfish/runtime-audit.md)，其等待登录状态已被本轮复测取代。
