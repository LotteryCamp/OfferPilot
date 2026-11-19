"""CLI for reading one public HTML source."""

import argparse
import json
import sys
from io import TextIOWrapper
from typing import Never
from uuid import UUID

from .reader import SourceReadError, read_public_html


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise SourceReadError("invalid_request", message)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = _JsonArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--scope-year", required=True, type=int)
    parser.add_argument("--scope")
    parser.add_argument("--title")
    parser.add_argument("--matter-id", type=UUID)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-fragments", type=int, default=4096)
    try:
        args = parser.parse_args()
        result = read_public_html(
            {
                "url": args.url,
                "publisher": args.publisher,
                "scope_year": args.scope_year,
                "scope": args.scope,
                "title": args.title,
                "matter_id": args.matter_id,
                "timeout_seconds": args.timeout,
                "max_bytes": args.max_bytes,
                "max_fragments": args.max_fragments,
            }
        )
    except SourceReadError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 2 if error.code == "invalid_request" else 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
