"""Sample local TaoDescribe/Products-10K files; annotate, then build eval JSON."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from evals.datasets import build_cases, file_hash, sample_products, sample_text, write_sample


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    text = commands.add_parser('taodescribe')
    source = text.add_mutually_exclusive_group(required=True)
    source.add_argument('--tsv')
    source.add_argument('--titles')
    text.add_argument('--descriptions')
    products = commands.add_parser('products10k')
    products.add_argument('--csv', required=True)
    products.add_argument('--images-root', required=True)
    for cmd in (text, products):
        cmd.add_argument('--count', type=int, default=8)
        cmd.add_argument('--seed', type=int, default=20261115)
        cmd.add_argument('--source-url', required=True)
        cmd.add_argument('--source-version', required=True)
        cmd.add_argument('--output', required=True)
    build = commands.add_parser('build')
    build.add_argument('--package', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            cases = build_cases(args.package)
            print(f'Built {len(cases)} cases in {Path(args.package).resolve() / "cases"}')
            return 0
        if not 1 <= args.count <= 10000:
            raise ValueError('count must be 1–10000')
        if args.command == 'taodescribe':
            if bool(args.titles) != bool(args.descriptions):
                raise ValueError('--titles requires --descriptions; do not combine --tsv with --descriptions')
            rows, stats = sample_text(count=args.count, seed=args.seed, tsv=args.tsv,
                                      titles=args.titles, descriptions=args.descriptions)
            files = [args.tsv] if args.tsv else [args.titles, args.descriptions]
        else:
            rows, stats = sample_products(csv_path=args.csv, images_root=args.images_root,
                                         count=args.count, seed=args.seed)
            files = [args.csv]
        metadata = {'dataset': args.command, 'source_url': args.source_url, 'source_version': args.source_version,
                    'seed': args.seed, 'sampling': 'sha256 order; one sample per title/SKU; no label inference',
                    'source_files': [{'name': Path(f).name, 'sha256': file_hash(f)} for f in files],
                    'sample_count': len(rows), **stats}
        output = write_sample(args.output, rows, metadata,
                              args.images_root if args.command == 'products10k' else None)
        print(f'Sampled {len(rows)} cases. Fill {output.resolve() / "annotations.json"}, then run build.')
        return 0
    except (ValueError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
