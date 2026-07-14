#!/usr/bin/env python3
import sys

from core.processor import run_processing


def main():
    try:
        result = run_processing(log=print)
    except Exception as e:
        print(f"エラー: {e}")
        sys.exit(1)

    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
