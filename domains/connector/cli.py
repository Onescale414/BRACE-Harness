"""Select a supported connector mapping and print a checked, read-only preview."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    from connector_selection import run_file
finally:
    sys.path.pop(0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('case', type=Path, help='Bound four-source case JSON; see README.md.')
    args = parser.parse_args(argv)
    code, result = run_file(args.case)
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
