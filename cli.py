from __future__ import annotations

import argparse
import json

from hub.adapters import convert_afs_csv
from hub.pipeline import PipelineOptions, ToolHubPipeline


def print_matches(matches: list[dict[str, str]]):
    if not matches:
        print("Keine Treffer gefunden.")
        return

    print(f"Gefundene Treffer: {len(matches)}")
    for index, match in enumerate(matches, start=1):
        print(f"{index:2d}. {match['cvcl']}  |  {match['name']}")


def main():
    parser = argparse.ArgumentParser(description="CellSearch Tool Hub CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Cellosaurus list-Suche")
    search_parser.add_argument("query", help="Suchbegriff fuer Cellosaurus")

    run_parser = subparsers.add_parser("run", help="Pipeline fuer eine ausgewaehlte Zelllinie starten")
    run_parser.add_argument("--search-query", required=True, help="Originaler Suchbegriff")
    run_parser.add_argument("--cvcl", required=True, help="Ausgewaehlter CVCL-Code")
    run_parser.add_argument("--name", required=True, help="Ausgewaehlter Zelllinienname")
    run_parser.add_argument("--sequential", action="store_true", help="Nebenjobs nacheinander ausfuehren")
    run_parser.add_argument("--skip-pubmed", action="store_true")
    run_parser.add_argument("--skip-descriptions", action="store_true")
    run_parser.add_argument("--skip-prices", action="store_true")

    afs_parser = subparsers.add_parser("afs", help="AFS-CSV konvertieren")
    afs_parser.add_argument("input_csv", help="Pfad zur Eingabe-CSV")
    afs_parser.add_argument("--output", help="Optionaler Ausgabepfad")

    args = parser.parse_args()
    pipeline = ToolHubPipeline(logger=print)

    if args.command == "search":
        matches = pipeline.search(args.query)
        print_matches(matches)
        return

    if args.command == "run":
        options = PipelineOptions(
            run_pubmed=not args.skip_pubmed,
            run_descriptions=not args.skip_descriptions,
            run_prices=not args.skip_prices,
            parallel=not args.sequential,
        )
        summary = pipeline.run(
            search_query=args.search_query,
            selected_cvcl=args.cvcl,
            selected_name=args.name,
            options=options,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if args.command == "afs":
        output_path = convert_afs_csv(args.input_csv, output_path=args.output)
        print(output_path)


if __name__ == "__main__":
    main()
