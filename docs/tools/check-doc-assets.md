# Markdown 本地资源引用检查

检查 Markdown 中的本地图片、PDF 和其他文件引用是否存在：

```bash
python tools/check_doc_assets.py docs --list-external
```

脚本识别 Markdown 行内链接、引用式链接和常见 HTML `src` / `href` 属性；围栏代码块与行内代码不会参与检查。网页链接只作为人工核对项列出，不判断其可访问性。脚本只读文件。

相对路径按所在 Markdown 的目录解析；空格可用 `%20` 或尖括号表示，文件后的查询串、页码和锚点会移除。以 `/` 开头的路径默认相对扫描目录解析；扫描 `docs` 时如需按仓库根目录解析，添加 `--root .`。引用指向目录时按目录存在处理。

- 退出码 `0`：本地引用均存在
- 退出码 `1`：至少有一条本地引用缺失
- 退出码 `2`：参数、扫描路径或文件读取错误

需要机器可读结果时可添加 `--json`；可用 `--skip-dir NAME` 增加跳过目录。

Windows 终端输出中文异常时，可使用 `python -X utf8 tools/check_doc_assets.py docs --list-external`。
