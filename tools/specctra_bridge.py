"""KiCad DSN export / SES import bridge for the Freerouting test."""

from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew


def export_dsn(board_path: Path, dsn_path: Path) -> None:
    board = pcbnew.LoadBoard(str(board_path.resolve()))
    if board is None:
        raise RuntimeError(f"Could not load {board_path}")
    if not pcbnew.ExportSpecctraDSN(board, str(dsn_path.resolve())):
        raise RuntimeError("KiCad failed to export Specctra DSN")


def import_ses(board_path: Path, ses_path: Path, output_path: Path) -> None:
    board = pcbnew.LoadBoard(str(board_path.resolve()))
    if board is None:
        raise RuntimeError(f"Could not load {board_path}")
    if not pcbnew.ImportSpecctraSES(board, str(ses_path.resolve())):
        raise RuntimeError("KiCad failed to import Freerouting SES")
    if not pcbnew.SaveBoard(str(output_path.resolve()), board):
        raise RuntimeError("KiCad failed to save the routed board")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("board", type=Path)
    export_parser.add_argument("dsn", type=Path)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("board", type=Path)
    import_parser.add_argument("ses", type=Path)
    import_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "export":
        export_dsn(args.board, args.dsn)
    else:
        import_ses(args.board, args.ses, args.output)


if __name__ == "__main__":
    main()
