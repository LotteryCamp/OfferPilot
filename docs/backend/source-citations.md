# Alpha 公开来源读取接口

本模块读取一份约定的公开 HTML 通知，返回可供当前事项和 Agent 引用的正文片段。HTML 是超文本标记语言，URL 是统一资源定位符，Agent 是项目中的领域智能体。

## 调用

从仓库的 `backend` 目录运行：

```powershell
uv run --locked python -m backend.sources https://math.fzu.edu.cn/info/1171/10393.htm --publisher "福州大学数学与统计学院" --scope-year 2027 --scope "2027 届、本院、校内推免推荐"
```

在后端代码中可以直接调用同一接口。如果调用方已经确认事项归属，可传入 `matter_id` 供后续关联。

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

定位使用现有证据类型中的 `section`、`text_span` 和 `table_row`。列表项按文本段编号，正文段编号包括列表项，章节标题和表格行使用各自的定位。后端接入时通过现有来源和快照流程登记版本号，按实际事项关联和授权保存出处。

读取只访问公开 HTTP/HTTPS 页面，校验每次跳转的目的地址，并限制总耗时和响应大小。地址不合规、网络失败、非 HTML、空正文或解析失败时，接口抛出 `SourceReadError`。命令行以非零状态退出，将错误码及是否可重试写入标准错误。

## 固定样例与复现

Alpha 样例 `FX-S4-2027-FZU-MATH` 使用福州大学数学与统计学院发布的 2027 年推免工作方案。发布日为 2026 年 9 月 8 日，原文第（5）项包含提交截止时间和材料要求。本通知的提交期限为 2026 年 9 月 10 日，用于历史回放。测试使用真实网页快照及其抓取时间，核对来源字段、快照标识、第（5）项定位和失败反馈。

```powershell
uv run --locked pytest tests/test_public_source_reader.py -q
```
