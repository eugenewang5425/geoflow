import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="GeoFlow Hadoop geospatial project")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Download public TLC data and prepare streaming CSV shards")
    ingest.add_argument("--month", default="2025-01")
    ingest.add_argument("--rows", type=int, default=0, help="0 = whole month")
    run = commands.add_parser("run", help="Submit a real YARN MapReduce job")
    run.add_argument("--month", default="2025-01")
    run.add_argument("--reducers", type=int, choices=range(1, 9), default=2)
    run.add_argument("--no-combiner", action="store_true")
    run.add_argument("--fail-first", action="store_true")
    commands.add_parser("serve", help="Serve the analysis dashboard on localhost:8765")
    args = parser.parse_args()
    if args.command == "ingest":
        from .ingest import ingest
        result = ingest(args.month, args.rows)
        print(json.dumps({k: v for k, v in result.items() if k != "shards"}, indent=2, ensure_ascii=False))
    elif args.command == "run":
        from .runner import run_job
        print(json.dumps(run_job(args.month, args.reducers, not args.no_combiner, args.fail_first),
                         indent=2, ensure_ascii=False))
    else:
        import uvicorn
        uvicorn.run("geoflow.api:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
