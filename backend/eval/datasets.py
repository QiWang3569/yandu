"""Dataset loading, splitting and SHA-256 freezing."""
import hashlib
import json
import subprocess
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent / 'datasets'
MANIFEST_PATH = DATASET_DIR / 'manifest.json'

NODE_FILES = {
    '1.1': 'item_text_1_1.jsonl',
    '1.2': 'vision_1_2.jsonl',
    '2.1': 'intent_2_1.jsonl',
    '2.3': 'recall_2_3.jsonl',
    '2.4': 'review_2_4.jsonl',
}
POOL_FILE = 'items_pool_2_3.jsonl'
IMAGES_DIR = DATASET_DIR / 'images'
SPLITS = ('dev', 'sealed_test')


def file_sha256(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def git_sha():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def read_rows(path):
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        row['_line'] = number
        rows.append(row)
    return rows


def load_rows(node, split='all'):
    if node not in NODE_FILES:
        raise KeyError(f'unknown node {node}')
    rows = read_rows(DATASET_DIR / NODE_FILES[node])
    if split in (None, 'all'):
        return rows
    if split not in SPLITS:
        raise ValueError(f'unknown split {split}')
    return [row for row in rows if row.get('split') == split]


def load_pool():
    return read_rows(DATASET_DIR / POOL_FILE)


def validate_rows(node, rows):
    """Structural checks that must hold before any paid call is made."""
    errors = []
    seen = set()
    for row in rows:
        for key in ('id', 'node', 'split', 'input', 'gold'):
            if key not in row:
                errors.append(f'{node}:{row.get("id", row["_line"])} missing {key}')
        if row.get('node') != node:
            errors.append(f'{node}:{row.get("id")} node mismatch {row.get("node")}')
        if row.get('split') not in SPLITS:
            errors.append(f'{node}:{row.get("id")} bad split {row.get("split")}')
        if row.get('id') in seen:
            errors.append(f'{node}:{row.get("id")} duplicate id')
        seen.add(row.get('id'))
        if node == '1.2':
            for image in row.get('input', {}).get('images', []):
                name = image.get('file')
                if name and not (DATASET_DIR / name).is_file():
                    errors.append(f'{node}:{row.get("id")} missing image {name}')
    return errors


def build_manifest(version, frozen_at, annotator):
    files = {}
    for name in (*NODE_FILES.values(), POOL_FILE):
        path = DATASET_DIR / name
        if not path.exists():
            raise FileNotFoundError(path)
        rows = read_rows(path)
        files[name] = {'sha256': file_sha256(path), 'rows': len(rows)}
    for path in sorted(IMAGES_DIR.glob('*.jpg')):
        files[f'images/{path.name}'] = {'sha256': file_sha256(path), 'bytes': path.stat().st_size}
    return {
        'schema': 1,
        'version': version,
        'frozen_at': frozen_at,
        'git_sha_at_freeze': git_sha(),
        'primary_annotator': annotator,
        'reviewed_fraction': 0.2,
        'double_annotated': ['2.1 roles/quotes', '2.4 verdicts'],
        'splits': {'dev': 0.4, 'sealed_test': 0.6},
        'files': files,
    }


def verify_manifest():
    """Return (ok, details). Any mismatch invalidates a real run."""
    if not MANIFEST_PATH.exists():
        return False, {'manifest': 'missing'}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    details = {'version': manifest.get('version'), 'mismatches': [], 'missing': []}
    for name, expected in manifest.get('files', {}).items():
        path = DATASET_DIR / name
        if not path.exists():
            details['missing'].append(name)
            continue
        actual = file_sha256(path)
        if actual != expected['sha256']:
            details['mismatches'].append({'file': name, 'expected': expected['sha256'], 'actual': actual})
    ok = not details['mismatches'] and not details['missing']
    return ok, details