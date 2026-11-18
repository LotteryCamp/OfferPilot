"""Validate an official-citation JSON file and print normalized JSON."""

import argparse
import json
import sys
from pathlib import Path

from .service import CitationValidationError, build_official_citations


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 official citation JSON file")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    except OSError, UnicodeError, json.JSONDecodeError:
        print(json.dumps({"error": "unreadable_json"}), file=sys.stderr)
        return 2
    try:
        result = build_official_citations(payload)
    except CitationValidationError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
