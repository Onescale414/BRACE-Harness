"""Read-only exact lookup in a bounded request/receipt capture."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
sys.path.pop(0)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise core.InputError('invalid-arguments')


def main(argv=None):
    try:
        parser = Parser(prog='receipt-inspector', description=__doc__, allow_abbrev=False)
        parser.add_argument('source', help='UTF-8 capture JSON file, or - for stdin.')
        parser.add_argument('--query', nargs=3, action='append', required=True,
                            metavar=('ACTION', 'STATUS', 'DECISION'))
        parser.add_argument('--strategy', choices=core.STRATEGIES, default='scan')
        args = parser.parse_args(argv)
        if not 1 <= len(args.query) <= core.MAX_QUERIES:
            raise core.InputError('query-count')
        for query in args.query:
            core.key(query)
        try:
            if args.source == '-':
                raw = sys.stdin.buffer.read(core.MAX_SOURCE_BYTES + 1)
            else:
                with open(args.source, 'rb') as source:
                    raw = source.read(core.MAX_SOURCE_BYTES + 1)
        except (OSError, ValueError):
            raise core.InputError('source-unavailable') from None
        result = core.inspect_source(raw, args.query, args.strategy)
    except core.InputError as exc:
        result = {'kind': 'receipt-inspection', 'status': 'withheld', 'reason': exc.reason}
        code = 2
    else:
        code = 0
    try:
        sys.stdout.buffer.write(core.encoded(result) + b'\n')
    except (OSError, BrokenPipeError):
        return 2
    return code


if __name__ == '__main__':
    raise SystemExit(main())
