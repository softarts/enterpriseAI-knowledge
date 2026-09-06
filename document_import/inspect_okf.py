"""Print the parsed record represented by an OKF file."""

import argparse
from pathlib import Path

from .okf import print_okf_record


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a parsed OKF record as JSON")
    parser.add_argument("file", type=Path, help="Path to an OKF .yaml file")
    args = parser.parse_args()
    print_okf_record(args.file)


if __name__ == "__main__":
    main()
