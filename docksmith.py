import argparse
import os
from build_engine import execute_build


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("-t", "--tag", default="myapp:latest")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("context", nargs="?", default=".")

    args = parser.parse_args()

    name, tag = args.tag.split(":")
    context = os.path.abspath(args.context)

    execute_build(name, tag, context, args.no_cache)


if __name__ == "__main__":
    main()