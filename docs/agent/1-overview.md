# Agent

此处放置 Agent 相关文档。总体设计请参见 [OfferPilot 领域 Agent 与软件系统集成设计](../design/agent-design/offerpilot-agent-design.md)。

出站字段白名单、来源筛选去重、响应与引文校验、错误码映射及 P0/P1 材料草拟授权边界参见 [Agent 出站字段、来源筛选与材料草拟授权契约](outbound-and-material-contract.md)。

后端业务服务通过 `AgentRunService` 创建、读取、确认、拒绝和取消运行。运行状态与检查点持久化，服务重启后可读取已保存结果并处理待确认候选；未完成的运行标记为中断，不恢复执行。运行使用进程内适配器调用来源服务、候选持久化服务与工作区校验，接口见 [核心业务流程 API](../backend/api.md)。
