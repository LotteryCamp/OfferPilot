#!/usr/bin/env python3
"""检查 Markdown 文档引用的本地文件是否存在。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_SKIP_DIRS = {
    ".git", ".github", "node_modules", ".venv", "venv",
    "__pycache__", "dist", "build", ".idea", ".vscode",
}
EXTERNAL_SCHEMES = {"http", "https", "ftp", "mailto", "tel", "data", "javascript"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico"}
DOCUMENT_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
}

INLINE_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(<[^>]*>|(?:[^()\s]|\([^()\s]*\))+)(?:\s+[\"'][^\"']*[\"'])?\s*\)"
)
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
HTML_REF_RE = re.compile(
    r"<(?:img|a|source|embed|object|iframe)\b[^>]*?(?<![\w-])(?:src|href)\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass
class Ref:
    md_file: str
    line: int
    raw: str
    target: Path | None
    kind: str
    external: bool = False

    def type_label(self) -> str:
        if self.external:
            return "外部链接"
        return {"image": "图片", "doc": "文档", "other": "文件"}[self.kind]


@dataclass
class Result:
    scanned_files: int = 0
    refs: list[Ref] = field(default_factory=list)
    missing: list[Ref] = field(default_factory=list)
    external: list[Ref] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def iter_markdown(root: Path, skip_dirs: set[str], errors: list[str]):
    """按路径顺序遍历 root 下的 Markdown 文件。"""
    def on_error(exc: OSError) -> None:
        errors.append(f"遍历失败：{exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames[:] = sorted(name for name in dirnames if name not in skip_dirs)
        for name in sorted(filenames):
            if name.lower().endswith((".md", ".markdown")):
                yield Path(dirpath) / name


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in DOCUMENT_SUFFIXES:
        return "doc"
    return "other"


def clean_target(raw: str) -> str:
    """去掉 Markdown 尖括号、查询串和锚点，并解码百分号路径。"""
    text = raw.strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    for separator in ("?", "#"):
        index = text.find(separator)
        if index >= 0:
            text = text[:index]
    return unquote(text)


def resolve(md_path: Path, raw: str, root: Path) -> tuple[Path | None, bool]:
    """将引用解析为磁盘路径，或标记为外部链接。"""
    text = raw.strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    if not text:
        return None, False
    if text.startswith("//"):
        return None, True

    parsed = urlparse(text)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES:
        return None, True
    if parsed.scheme and len(parsed.scheme) > 1:
        return None, True

    cleaned = clean_target(text).replace("\\", "/")
    if not cleaned:
        return None, False

    if len(parsed.scheme) == 1 and text[1:3] in {":/", ":\\"}:
        return Path(cleaned).resolve(), False
    if cleaned.startswith("/"):
        return (root / cleaned.lstrip("/")).resolve(), False
    return (md_path.parent / cleaned).resolve(), False


def record_ref(
    result: Result,
    md_path: Path,
    root: Path,
    lineno: int,
    raw: str,
) -> None:
    try:
        rel_md = md_path.relative_to(root).as_posix()
    except ValueError:
        rel_md = str(md_path)

    target, external = resolve(md_path, raw, root)
    if external:
        ref = Ref(rel_md, lineno, raw.strip(), None, "other", True)
        result.external.append(ref)
        return
    if target is None:
        return

    ref = Ref(rel_md, lineno, raw.strip(), target, classify(target))
    result.refs.append(ref)
    if not target.exists():
        result.missing.append(ref)


def scan_file(md_path: Path, root: Path, result: Result) -> None:
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.errors.append(f"读取失败：{md_path}（{exc}）")
        return

    result.scanned_files += 1
    in_fence = False
    fence_char = ""
    fence_length = 0

    for lineno, line in enumerate(text.splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_length = len(marker)
                continue
            if marker[0] == fence_char and len(marker) >= fence_length:
                in_fence = False
                continue
        if in_fence:
            continue

        probe = INLINE_CODE_RE.sub("", line)
        for match in INLINE_LINK_RE.finditer(probe):
            record_ref(result, md_path, root, lineno, match.group(1))

        ref_def = REF_DEF_RE.match(probe)
        if ref_def:
            record_ref(result, md_path, root, lineno, ref_def.group(1))

        for match in HTML_REF_RE.finditer(probe):
            record_ref(result, md_path, root, lineno, match.group(1))


def print_report(result: Result, root: Path, show_external: bool) -> None:
    if result.missing:
        print("缺失的引用：")
        for ref in result.missing:
            try:
                shown = ref.target.relative_to(root).as_posix()
            except ValueError:
                shown = str(ref.target)
            print(f"  {ref.md_file}:{ref.line}: {ref.type_label()}不存在  {ref.raw}")
            print(f"      解析为 {shown}")
        print()

    for error in result.errors:
        print(error, file=sys.stderr)

    if show_external and result.external:
        print("外部链接（不检查可访问性，请人工确认）：")
        for ref in result.external:
            print(f"  {ref.md_file}:{ref.line}: {ref.raw}")
        print()

    print(
        f"扫描 {result.scanned_files} 个 Markdown 文件，"
        f"检查 {len(result.refs)} 条本地引用，"
        f"缺失 {len(result.missing)} 条，"
        f"外部链接 {len(result.external)} 条，"
        f"读取错误 {len(result.errors)} 条。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="检查 Markdown 中引用的本地文件是否存在（只读）",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], help="要扫描的文件或目录，默认当前目录"
    )
    parser.add_argument(
        "--root", default=None,
        help="解析以 / 开头的引用时使用的仓库根目录，默认取第一个扫描路径",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument(
        "--list-external", action="store_true", help="列出外部链接供人工确认"
    )
    parser.add_argument(
        "--skip-dir", action="append", default=[], help="额外跳过的目录名，可重复"
    )
    args = parser.parse_args(argv)

    targets = [Path(path) for path in (args.paths or ["."])]
    missing_paths = [path for path in targets if not path.exists()]
    if missing_paths:
        for path in missing_paths:
            print(f"路径不存在：{path}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve() if args.root else (
        targets[0].resolve() if targets[0].is_dir() else targets[0].resolve().parent
    )
    if args.root and not root.is_dir():
        print(f"根目录不存在或不是目录：{root}", file=sys.stderr)
        return 2

    skip_dirs = DEFAULT_SKIP_DIRS | set(args.skip_dir)
    result = Result()
    for target in targets:
        target = target.resolve()
        if target.is_file():
            if target.suffix.lower() in {".md", ".markdown"}:
                scan_file(target, root, result)
        elif target.is_dir():
            for md_path in iter_markdown(target, skip_dirs, result.errors):
                scan_file(md_path, root, result)

    if args.json:
        payload = {
            "root": str(root),
            "scannedFiles": result.scanned_files,
            "checkedRefs": len(result.refs),
            "missing": [
                {
                    "file": ref.md_file,
                    "line": ref.line,
                    "ref": ref.raw,
                    "resolved": str(ref.target),
                    "type": ref.kind,
                }
                for ref in result.missing
            ],
            "external": [
                {"file": ref.md_file, "line": ref.line, "ref": ref.raw}
                for ref in result.external
            ],
            "errors": result.errors,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_report(result, root, args.list_external)

    if result.errors:
        return 2
    return 1 if result.missing else 0


if __name__ == "__main__":
    sys.exit(main())
