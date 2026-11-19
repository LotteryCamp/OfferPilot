"""Recheck the five public items in this fixture. Report clause changes without rewriting evidence."""

from __future__ import annotations

import hashlib
import re
import ssl
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from html.parser import HTMLParser
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener, getproxies_environment
from xml.etree import ElementTree
from zipfile import ZipFile

from verify import indexed, load_file, require

HOSTS = {"math.fzu.edu.cn", "jgxy.fzu.edu.cn", "radio.seu.edu.cn"}
MAX_BYTES = 2_000_000
SOURCE_TIMEOUT = 15
ATTEMPT_TIMEOUT = 6
RETRY_DELAYS = (0, 0.25, 0.75)
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}
TEMPORARY_FAILURE = 75


def check_url(url):
    parts = urlsplit(url)
    require(parts.scheme == "https" and parts.hostname in HOSTS and not parts.username
            and not parts.password and parts.port in {None, 443}, "地址超出本批学校官网范围")


class SchoolRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        check_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(text):
    return re.sub(r"[\s\x07]+", "", unicodedata.normalize("NFKC", text))


def extract(src, raw):
    if src["format"] == "html":
        page = Page()
        page.feed(raw.decode("utf-8-sig"))
        return normalize("".join(page.parts)), {urljoin(src["url"], link) for link in page.links}
    if src["format"] == "docx":
        with ZipFile(BytesIO(raw)) as doc:
            root = ElementTree.fromstring(doc.read("word/document.xml"))
        text = "".join(
            node.text or "" for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        )
        return normalize(text), set()
    # The verified legacy Word file contains this row as consecutive UTF-16LE
    # table cells. Keep this narrow check tied to the original archived binary.
    require(src["source_id"] == "S5-A1" and raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")),
            "招生目录的文件格式已变化")
    require(hashlib.sha256(raw).hexdigest() == src["sha256"], "招生目录已换版，需在原表重新核对行列")
    require("学术型硕士\x07020100\x07理论经济学\x07".encode("utf-16-le") in raw,
            "招生目录未定位到学位类型、代码与专业名的相邻单元格")
    return normalize(raw.decode("utf-16-le", errors="ignore")), set()


def check_citations(text, citations):
    for code, c in citations:
        start = text.find(normalize(c["section_start"]))
        end = text.find(normalize(c["section_end"]), start + len(normalize(c["section_start"])))
        require(0 <= start < end, f"{code} 无法定位 {c['locator']}")
        section = text[start:end]
        for term in [c["excerpt"], *c["keywords"]]:
            require(normalize(term) in section, f"{code} 条款内找不到“{term}”")


def download_once(source_id):
    sources = indexed(load_file("sources.json")["sources"], "source_id")
    src = sources[source_id]
    check_url(src["url"])
    headers = {"User-Agent": "OfferPilot-course-fixture/1.1", "Accept-Encoding": "identity"}
    if src.get("parent_source_id"):
        headers["Referer"] = sources[src["parent_source_id"]]["url"]
    request = Request(src["url"], headers=headers)
    opener = build_opener(ProxyHandler(getproxies_environment()), SchoolRedirects())
    with opener.open(request, timeout=ATTEMPT_TIMEOUT) as response:
        require(response.status == 200, f"HTTP {response.status}")
        raw = response.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "响应超过样例核对上限")
    return raw


def download_worker(source_id):
    try:
        raw = download_once(source_id)
    except HTTPError as error:
        print(error, file=sys.stderr)
        return TEMPORARY_FAILURE if error.code in TRANSIENT_HTTP else 1
    except URLError as error:
        print(error, file=sys.stderr)
        return 1 if isinstance(error.reason, ssl.SSLCertVerificationError) else TEMPORARY_FAILURE
    except (TimeoutError, ConnectionError, HTTPException) as error:
        print(error, file=sys.stderr)
        return TEMPORARY_FAILURE
    sys.stdout.buffer.write(raw)
    return 0


def download_source(source_id):
    command = [sys.executable, "-B", "-X", "utf8", __file__, "--download-source", source_id]
    expires = time.monotonic() + SOURCE_TIMEOUT
    last_error = "已达到总时限"
    # Bound the worker from outside urllib so slow streaming cannot extend its deadline.
    for delay in RETRY_DELAYS:
        if expires - time.monotonic() <= delay:
            break
        time.sleep(delay)
        remaining = expires - time.monotonic()
        if remaining <= 0:
            break
        try:
            attempt = subprocess.run(
                command, capture_output=True, timeout=min(remaining, ATTEMPT_TIMEOUT),
                check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            last_error = "请求或读取超时"
            continue
        if attempt.returncode == 0:
            return attempt.stdout
        error_lines = attempt.stderr.decode("utf-8", errors="replace").strip().splitlines()
        last_error = error_lines[-1] if error_lines else f"下载进程退出码 {attempt.returncode}"
        if attempt.returncode != TEMPORARY_FAILURE:
            raise ValueError(last_error)
    raise ValueError(f"来源请求重试结束（{SOURCE_TIMEOUT}秒预算），{last_error}")


def main():
    sources = indexed(load_file("sources.json")["sources"], "source_id")
    rules = load_file("rules.json")["rules"]
    citations = {s["source_version_id"]: [] for s in sources.values()}
    for r in rules:
        for c in r["basis"] + r.get("fallback_basis", []):
            citations[c["source_version_id"]].append((r["requirement_id"], c))
    link_sets, failures = {}, []
    print("核对时点", datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"))
    for sid, src in sources.items():
        try:
            raw = download_source(sid)
            content, link_sets[sid] = extract(src, raw)
            if src["format"] == "html":
                require(normalize(src["title"]) in content, "页面题名不符")
                require(src["published_on"] in content, "页面发布日期不符")
            refs = citations[src["source_version_id"]]
            check_citations(content, refs)
            digest = hashlib.sha256(raw).hexdigest()
            version = "与留存摘要相同" if digest == src["sha256"] else "响应字节有变化，已核对所列条款，旧版本继续保留"
            print(f"{sid}  HTTP 200  {len(raw)} B  {len(refs)} 处定位  {digest[:12]}  {version}")
        except Exception as error:
            failures.append(f"{sid} 读取或定位失败：{error}")
    for sid, src in sources.items():
        parent = src.get("parent_source_id")
        if parent and src["url"] not in link_sets.get(parent, set()):
            failures.append(f"{sid} 未能从 {parent} 正文回查到附件链接")
    if failures:
        sys.exit("\n".join(failures))
    print("正文、附件所属通知及条款定位核对通过。")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--download-source":
        sys.exit(download_worker(sys.argv[2]))
    main()
