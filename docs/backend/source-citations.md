# Alpha 公开来源读取接口

本模块读取一份约定的公开 HTML 通知，返回可供当前事项和 Agent 引用的正文片段。HTML 是超文本标记语言，URL 是统一资源定位符，Agent 是项目中的领域智能体。

## 调用

从仓库的 `backend` 目录运行：

```powershell
uv run --locked python -m backend.sources https://math.fzu.edu.cn/info/1171/10393.htm --publisher "福州大学数学与统计学院" --scope-year 2027 --scope "2027 届、本院、校内推免推荐"
```

在后端代码中可以直接调用同一接口。

```python
from backend.sources import SourceReadError, read_public_html

try:
    source = read_public_html({
        "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
        "publisher": "福州大学数学与统计学院",
        "scope_year": 2027,
        "scope": "2027 届、本院、校内推免推荐",
    })
except SourceReadError as error:
    failure = error.as_dict()
```

| 返回字段 | 含义 |
| :--- | :--- |
| `url`、`title`、`publisher`、`published_date` | 最终 URL、网页标题、调用方给定的发布主体、网页明确标出的发布日期 |
| `scope_year`、`scope` | 调用方按约定样例提供的适用年度与范围 |
| `fetched_at` | 本次成功获取网页的时间 |
| `source_id`、`snapshot_id`、`content_hash` | 由最终 URL 生成的来源标识，以及由 URL 和原始响应摘要生成的快照标识。同一 URL 和内容可重现同一快照标识 |
| `matter_id` | 调用方传入的事项标识 |
| `normalized_text`、`fragments` | 规范化正文和按原文顺序整理的片段。每个片段含原文、结构化位置和可读位置 |

定位使用现有证据类型中的 `section`、`text_span` 和 `table_row`。列表项按文本段编号，章节标题和表格行使用各自的定位。

读取只访问公开 HTTP/HTTPS 页面，校验每次跳转的目的地址，并限制总耗时和响应大小。地址不合规、网络失败、非 HTML、空正文或解析失败时，接口抛出 `SourceReadError`。命令行以非零状态退出，将错误码及是否可重试写入标准错误。

## 事项接入和引用

1. 前端在已确认归属的事项下调用 [业务接口](api.md) `POST /api/v1/matters/{matter_id}/sources/read`，请求体包含 `url`、`publisher`、`scope_year` 和可选的 `scope`、`title`。业务接口读取公开 HTML 页面，保存共享来源、快照和原文片段，并返回 `source`、`snapshot`、`created` 与 `document`。
2. `document` 是 Agent 输入，包含登记后的来源与快照标识、版本号、获取时间、来源状态和原文片段。Agent 用它生成要求与出处。
3. Agent 将生成的要求和出处交给同一事项的 `POST /api/v1/matters/{matter_id}/requirements`。业务接口通过要求与快照建立事项关联，要求保存后可用 `GET /api/v1/matters/{matter_id}/sources` 回看。

需要分别控制读取与登记两个阶段时，可以直接调用本模块：用 `source_registration_payload(result)` 生成 `POST /api/v1/matters/{matter_id}/sources` 的请求体，登记成功后用 `source_document_from_registration(response)` 生成 Agent 输入。登记返回的来源标识、快照标识和版本号优先于读取阶段的临时结果。

## 固定样例与复现

Alpha 样例 `FX-S4-2027-FZU-MATH` 使用福州大学数学与统计学院发布的 2027 年推免工作方案。发布日为 2026 年 9 月 8 日，原文第（5）项包含提交截止时间和材料要求。本通知的提交期限为 2026 年 9 月 10 日，用于历史回放。测试使用真实网页快照及其抓取时间，核对来源字段、快照标识、第（5）项定位和失败反馈。

接口联调由 `tests/test_api_flow.py` 中的 `test_read_public_source_registers_snapshot_for_citation` 覆盖：使用同一网页快照回放读取，经业务接口登记来源与快照，再用返回的片段写入要求并读取来源链。该测试需要 PostgreSQL 测试库。

```powershell
uv run --locked pytest tests/test_public_source_reader.py -q
```
