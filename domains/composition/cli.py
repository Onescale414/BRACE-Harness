"""Bounded composition sessions: NDJSON requests and explicit lesson acceptance."""
import argparse
from pathlib import Path
import sys

# Support the documented isolated invocation from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import learning_session
sys.path.pop(0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--store', metavar='ABSOLUTE_DIRECTORY',
                        help='Host-selected local lesson store; omitted means memory only.')
    parser.add_argument('--rollback', action='store_true',
                        help='Recheck and restore the previous accepted store generation.')
    args = parser.parse_args(argv)
    if args.rollback and args.store is None:
        parser.error('--rollback requires --store')
    if args.rollback:
        try:
            result = learning_session.rollback_store(args.store)
        except (OSError, ValueError, RuntimeError) as exc:
            result = {'decision': 'withhold', 'status': 'store-unavailable',
                      'error': str(exc)[:160]}
            code = 1
        else:
            code = 0
        print(learning_session.encoded(result).decode('ascii'), flush=True)
        return code
    return learning_session.serve(sys.stdin.buffer, sys.stdout, store_path=args.store)


if __name__ == '__main__':
    raise SystemExit(main())
