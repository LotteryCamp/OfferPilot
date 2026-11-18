# 来源与引用处理接口

`offerpilot-citations` 整理公开来源元数据、检查引用完整性，输出来源页面和材料预览可用的引用清单。实现位于 `packages/citations`，使用 Python 3.14、UV 和 Pydantic。输入与输出均采用 JSON（JavaScript Object Notation）兼容结构。

## 1. 运行

从仓库根目录执行：

```bash
uv sync --project packages/citations --locked
uv run --project packages/citations --locked offerpilot-citations packages/citations/examples/fzu_notice.json
uv run --project packages/citations --locked pytest packages/citations/tests -q
uv run --project packages/citations --locked ruff check packages/citations
```

命令行使用 UTF-8 输出。成功时向标准输出返回完整 JSON，退出码为 `0`；字段或一致性校验失败时向标准错误返回缺口清单，退出码为 `1`；文件读取或 JSON 解析失败为 `2`。不返回部分成功结果，错误中只包含字段路径和错误码。

应用可通过以下命令安装本模块：

```bash
uv add ./packages/citations
```

该命令在调用方的 Python 项目中执行。模块作为独立包提供，后端与 Agent 可以通过同一 Python 接口调用。

## 2. 公开引用接口

```python
from offerpilot_citations import CitationValidationError, build_official_citations

try:
    citation_list = build_official_citations(payload)
except CitationValidationError as error:
    gaps = error.as_dict()
```

### 2.1 输入

顶层字段为 `scope_year`、`snapshots`、`citations`。`scope_year` 是本次事项需要的适用年度，例如 2027，独立于发布日期与获取年份。所有输入对象拒绝未声明字段。

`snapshots` 是检索服务或后端提供的来源与快照关联视图：

| 字段 | 类型 | 含义 |
| :--- | :--- | :--- |
| `origin` | 固定字符串 `official_retrieval` | 由可信检索入口提供的来源类别；用户上传件使用各自的私有资料流程 |
| `source_id` | UUID 字符串 | 后端登记的来源标识，UUID 为通用唯一识别码 |
| `snapshot_id` | UUID 字符串 | 后端登记的具体快照标识 |
| `version_no` | 正整数 | 快照版本，和同一来源组合时必须唯一 |
| `url` | HTTP/HTTPS URL | 实际引用正文或附件的地址，URL 为统一资源定位符；上限 500 字符 |
| `title` | 非空字符串 | 通知或附件标题 |
| `publisher` | 非空字符串 | 发布主体，上限 160 字符 |
| `scope_year` | 整数，2020—2100 | 官方材料适用年度，由上游根据原文提供 |
| `fetched_at` | 带时区的 ISO 8601 时间 | 此快照的实际获取时间；统一输出为协调世界时（UTC） |

`citations` 中每条公开引用包含：

| 字段 | 类型 | 含义 |
| :--- | :--- | :--- |
| `kind` | 固定字符串 `official` | 公开规则引用类别 |
| `source_id`、`snapshot_id` | UUID 字符串 | 指向 `snapshots` 中同一来源的具体版本 |
| `fetched_at` | 带时区的时间 | 必须与对应快照的获取时刻一致 |
| `locator` | 定位对象 | 明确指向章节、页码、段落字符区间或表格行 |
| `quote` | 可选非空字符串 | 原文摘录；提供时去除两端空白，并计算 SHA-256 摘要 |

定位格式：

```json
{"kind": "section", "section": "第（4）项"}
{"kind": "page", "page": 3, "end_page": 5}
{"kind": "text_span", "paragraph": 4, "start": 0, "end": 18}
{"kind": "table_row", "table": "材料清单", "row": 2}
```

以上四行分别是独立的定位对象。页码、段落和数据行从 1 开始；字符区间采用 Python 的 `[start:end]`，从 0 开始，结束位置不包含在内。段落划分由对应快照的提取器固定；`table` 使用提取器提供的表标识或标题，`row` 是该表数据行号。引用附件页码时，`url` 应指向实际附件，页码由附件读取工具提供。

### 2.2 输出

返回 `scope_year` 与 `citations`。每条结果保留来源、快照、版本、适用年度、获取时间和结构化定位，并增加：

| 字段 | 用途 |
| :--- | :--- |
| `locator_text` | 可读定位，例如“第3—5页” |
| `citation_text` | 页面展示文字，包含标题、发布主体、适用年度与位置 |
| `quote_hash` | 仅提供摘录时返回，其 UTF-8 字节的 SHA-256 摘要 |
| `basis` | `{source_id, snapshot_id, locator, fetched_at}` 证据四元组 |

同一来源、快照、时刻和定位的完全相同引用合并，保留首次出现顺序；同一定位对应不同摘录时返回 `conflicting_quote`，交上游明确处理。多个历史快照分别保留。展示端应将所有文本字段当作纯文本渲染。

### 2.3 缺口与错误

```json
{
  "error": "invalid_citations",
  "issues": [
    {"path": "citations.0.locator", "code": "missing_field"}
  ]
}
```

| 错误码 | 处理方式 |
| :--- | :--- |
| `missing_field`、`string_too_short` | 补齐实际元数据或定位；保持待补状态 |
| `extra_forbidden`、`literal_error` | 按接口拆分公开规则与个人引用，检查字段及来源类别 |
| `unknown_snapshot` | 由后端提供对应快照视图 |
| `source_snapshot_mismatch`、`snapshot_time_mismatch` | 核对来源、快照和实际获取时间 |
| `scope_year_mismatch` | 核对事项年度及引用依据 |
| `duplicate_snapshot`、`duplicate_snapshot_version` | 核对来源快照登记结果 |
| `conflicting_quote`、`locator_collision` | 明确原文位置和摘录，避免重复登记歧义 |
| `page_range`、`text_span_range` | 使用读取工具提供的有效区间 |

其他类型、格式与长度错误保留 Pydantic 的稳定错误码，字段路径用于定位。模块不填写默认页码、虚构来源、推测年份或生成缺失快照标识。

### 2.4 公开来源读取器

`offerpilot-source-reader` 是面向可信来源适配器的首版读取入口。它只读取公开的 HTTP/HTTPS HTML 页面，并将页面内容转换为可关联事项、可复核的来源快照。读取成功后返回规范化文本、最终 URL、标题、发布主体、适用年度、获取时间、内容摘要和原文片段定位；传入 `matter_id` 时，结果可以直接关联到个人事项。

```bash
uv run --project packages/citations --locked offerpilot-source-reader \
  https://math.fzu.edu.cn/info/1171/10393.htm \
  --publisher "福州大学数学与统计学院" \
  --scope-year 2027 \
  --matter-id 3e8d27b5-07d4-44ca-bae5-f2f4e57bf631
```

需要在读取后登记时追加 `--database offerpilot.db`；该选项返回已登记的事项关联和引用片段。

命令成功退出码为 `0`，标准输出返回 `status="success"` 的 JSON。结果中的 `source_id` 按最终 URL 稳定生成，`snapshot_id` 按最终 URL 与内容摘要生成；同一页面内容再次读取时可以识别为同一快照。`fragments` 保存标题、段落、列表和表格单元格等可读块，每一项包含 `quote`、`locator` 和 `locator_text`。`citation_batch()` 可以将读取结果转换为本模块的公开引用校验输入。`--max-bytes` 和 `--max-fragments` 用于限制单次读取的响应大小和可保留片段数量。

读取失败时不返回成功对象，也不生成空白规则结论，而是向标准错误返回结构化错误并以非零退出码结束：

| 错误码 | 说明 |
| :--- | :--- |
| `invalid_request` | 必填参数或参数范围不符合接口契约 |
| `unsafe_url` | 不是公开 HTTP/HTTPS 地址、包含账号密码，或解析到环回、私有、链路本地和保留地址 |
| `network_error` | DNS、连接或超时失败，可重试 |
| `http_error` | 页面返回 HTTP 错误状态 |
| `unsupported_content_type` | 响应不是 `text/html` 或 `application/xhtml+xml` |
| `response_too_large` | 响应超过读取上限 |
| `empty_content` | 页面没有可读取文本 |
| `too_many_fragments` | 页面可读区块超过片段数量上限 |
| `decode_error`、`parse_error` | 页面编码或 HTML 解析失败 |

首版支持范围限定为公开 HTML；不承诺任意 PDF、扫描件、需要登录的页面、依赖浏览器执行 JavaScript 才能生成正文的复杂网页。PDF 或附件应由专门的附件读取流程提取定位后，再送入公开引用接口。读取器也不替业务层完成官方身份核实、政策资格判断或数据库写入；这些动作由后端和领域 Agent 的授权流程负责。

### 2.5 来源登记与 Agent 引用

读取器返回 `PublicSourceResult` 后，后端使用调用方拥有的 SQLite 数据库登记来源、快照、事项关联和证据片段：

```python
from offerpilot_citations import SourceRegistry, read_public_html

result = read_public_html(request)
registry = SourceRegistry("offerpilot.db")
try:
    registered = registry.register(result)
finally:
    registry.close()
```

登记器创建 `source`、`source_snapshot`、`source_matter` 和 `source_evidence` 表。相同 `snapshot_id` 重复登记时复用已登记的版本号和获取时间；同一来源出现内容变化时，按数据库中已有的最大版本号递增。返回的 `registered["citations"]` 只包含来源标识、快照标识、版本、获取时间、定位和原文摘录，可作为 Agent 的引用上下文；数据库连接、事项授权和事实内容不返回给模型。来源或快照发生冲突时返回 `source_registration_failed/registration_conflict`，调用方应停止生成结论并交由人工或后端处理。

## 3. 私有事实引用

```python
from uuid import UUID
from offerpilot_citations import build_fact_references

refs = build_fact_references(
    private_references,
    current_user_id=UUID(authenticated_user_id),
    matter_id=UUID(authorized_matter_id),
)
```

每条输入包含 `kind="personal_fact"`、`owner_id`、`matter_id`、`fact_id`、正整数 `fact_version`、带时区的 `confirmed_at`。输出只包含这组引用标识，不接受成绩、经历、文件正文等事实值。

调用方从已认证会话和已授权事项取得上下文，并在调用前检查事实的当前版本、确认状态、使用授权和撤回状态。模块比较上下文中的所有者和事项，失配时返回 `owner_mismatch` 或 `matter_mismatch`；事实引用通过单独的接口返回，不能送进公开引用清单。向外部模型发送数据时，仍由业务服务逐次检查传输同意。

## 4. 与数据模型的对应

| 模块字段 | 数据库字段 |
| :--- | :--- |
| `source_id`、`url`、`publisher`、`scope_year` | `ops.source.id/url/publisher/scope_year` |
| `snapshot_id`、`version_no`、`fetched_at` | `ops.snapshot.id/version_no/fetched_at` |
| `basis`、`locator.kind`、`locator_text`、`quote`、`quote_hash` | `ops.evidence` 的证据四元组、`locator_kind`、`locator`、摘录与摘要 |
| `fact_id`、`fact_version`、`confirmed_at` | `core.fact.id/version_no/confirmed_at` |

`origin` 和 `title` 为检索适配视图的字段，当前来源表没有对应列。业务对象的 `target_type`、`target_id` 由调用方写证据时提供。页面信息来自快照视图，数据库的写入、授权及并发版本检查由后端完成。

## 5. 真实通知样例

`packages/citations/examples/fzu_notice.html` 是[福州大学数学与统计学院2027年推免工作方案](https://math.fzu.edu.cn/info/1171/10393.htm)的公开 HTML 快照，`fzu_notice.json` 使用其中第（4）项的一句公开摘录，来源已列在团队领域资料索引 S4 中。实际获取时间、页面编码摘要及样例标识生成方法见同目录的 `fzu_notice_provenance.json`。

本样例的适用年度为 2027，发布日期和本次获取年份为 2026。该通知的申请期已经结束，用于验证引用处理。样例标识由实际 URL 与获取内容的摘要派生，仅用于本地演示；接入后使用后端登记的来源和快照标识。例中的版本 1 是本地样例版本。

公开引用校验接口处理上游已经取得的内容与定位；公开来源读取器负责首版 HTML 下载和正文定位。两者都不执行附件解析、官方身份核实、政策资格判断或数据库写入。结构校验通过表示字段完整且关联一致；原文能否支撑业务结论仍需结合领域规则核对。`origin` 应由可信采集适配器填写，用户请求体中的自述类别不能替代来源分层检查。

## 6. 检查

测试直接调用实现，使用真实通知快照验证正文、标题、定位、快照标识和引文适配；同时覆盖字段缺失、版本不匹配、跨年、重复、页码、时区、片段上限和公开/私有边界输入。测试中的私人标识为测试专用，不包含真实学生资料。测试不把本地快照描述为远程业务链路验收。

接入顺序：检索与后端提供来源快照视图及原文定位；调用公开引用接口；将缺口反馈给原流程；成功结果供页面和材料预览读取。个人事实由已授权业务接口单独提供引用标识。真实通知样例可用于双方确认字段与返回格式。

读取器的验证命令：

```bash
uv run --project packages/citations --locked pytest -q
uv run --project packages/citations --locked ruff check .
uv run --project packages/citations --locked ruff format --check .
```

这些命令覆盖来源契约、真实通知快照解析、CLI 错误输出、代码检查和格式检查。它们通过后，读取结果可交给后端的来源登记与引文校验流程；这不代表完整 Alpha 业务流程已经联调。
