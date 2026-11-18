"""CLI for reading one public HTML source."""

import argparse
import json
import sys
from uuid import UUID

from pydantic import ValidationError

from .reader import SourceReadError, read_public_html
from .registry import SourceRegistrationError, SourceRegistry


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SourceReadError("invalid_request", message)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = _JsonArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--scope-year", required=True, type=int)
    parser.add_argument("--title")
    parser.add_argument("--matter-id", type=UUID)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-fragments", type=int, default=4096)
    parser.add_argument("--database", help="Register the result in this SQLite database")
    try:
        args = parser.parse_args()
        result = read_public_html(
            {
                "url": args.url,
                "publisher": args.publisher,
                "scope_year": args.scope_year,
                "title": args.title,
                "matter_id": args.matter_id,
                "timeout_seconds": args.timeout,
                "max_bytes": args.max_bytes,
                "max_fragments": args.max_fragments,
            }
        )
        if args.database:
            registry = SourceRegistry(args.database)
            try:
                registered = registry.register(result)
            finally:
                registry.close()
            print(json.dumps(registered, ensure_ascii=False, indent=2))
            return 0
    except SourceRegistrationError:
        print(
            json.dumps({"error": "source_registration_failed", "code": "registration_conflict"}),
            file=sys.stderr,
        )
        return 1
    except (ValidationError, SourceReadError) as error:
        if isinstance(error, SourceReadError):
            payload = error.as_dict()
            exit_code = 1 if error.code != "invalid_request" else 2
        else:
            payload = {"error": "source_read_failed", "code": "invalid_request"}
            exit_code = 2
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return exit_code
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
