# Agent

此处放置 Agent 相关文档。总体设计请参见 [OfferPilot 领域 Agent 与软件系统集成设计](../design/agent-design/offerpilot-agent-design.md)。

后端业务服务通过 `AgentRunService` 创建、读取、确认、拒绝和取消运行。运行状态与检查点持久化，服务重启后可读取已保存结果并处理待确认候选；未完成的运行标记为中断，不恢复执行。运行使用进程内适配器调用来源服务、候选持久化服务与工作区校验，接口见 [Alpha 核心业务流程 API](../backend/api.md)。
