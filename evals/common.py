"""Small deterministic serialization helpers shared by the evaluation CLI."""
import hashlib
import json
from pathlib import Path


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def read_json(path):
    def reject_constant(value):
        raise ValueError(f'Non-finite JSON number: {value}')

    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject_constant)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
