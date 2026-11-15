"""Freeze existing synthetic and locally imported public cases into an empty directory."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from evals.common import digest, write_json
from evals.schema import validate_cases


def build(output, public_cases):
    cases = []
    for source in (ROOT / 'evals/cases', ROOT / 'evals/search_benchmark/cases', public_cases):
        cases.extend(validate_cases(source))
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate case IDs across sources')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty')
    output.mkdir(parents=True, exist_ok=True)
    for case in cases:
        write_json(output / (case['id'] + '.json'), case)
    frozen = validate_cases(output)
    print(f'Frozen {len(frozen)} cases; dataset_hash={digest(frozen)}')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-cases', type=Path,
                        default=ROOT / 'data/public-eval/taodescribe-pilot/cases')
    args = parser.parse_args()
    build(args.output, args.public_cases)
