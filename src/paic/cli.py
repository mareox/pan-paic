"""PAIC command-line interface."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as pkg_version


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "paic.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="paic",
        description="Prisma Access IP Console",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"paic {pkg_version('paic')}",
    )

    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Start the PAIC API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")
    serve_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        _serve(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
