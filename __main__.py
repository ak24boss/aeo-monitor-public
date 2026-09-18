from cli import build_parser, cmd_run

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args)
