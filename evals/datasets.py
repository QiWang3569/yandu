"""Small reproducible public-data samples, with a separate annotation step."""
import csv
import hashlib
from itertools import zip_longest
from pathlib import Path, PurePosixPath
import shutil

from .common import digest, read_json, write_json
from .schema import Case


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def taodescribe_rows(*, tsv=None, titles=None, descriptions=None):
    if tsv:
        with Path(tsv).open(encoding='utf-8-sig') as stream:
            for index, line in enumerate(stream, 1):
                fields = line.rstrip('\r\n').split('\t')
                if len(fields) != 2:
                    raise ValueError(f'TaoDescribe line {index}: expected title and description')
                yield str(index), *fields
    else:
        with Path(titles).open(encoding='utf-8-sig') as first, Path(descriptions).open(encoding='utf-8-sig') as second:
            for index, pair in enumerate(zip_longest(first, second), 1):
                if None in pair:
                    raise ValueError('TaoDescribe title/description line counts differ')
                yield str(index), *(text.rstrip('\r\n') for text in pair)


def sample_text(*, count, seed, tsv=None, titles=None, descriptions=None):
    candidates, excluded = {}, 0
    for source_id, title, description in taodescribe_rows(tsv=tsv, titles=titles, descriptions=descriptions):
        title, description = title.strip(), description.strip()
        text = title + '\n' + description
        if not title or not description or not 5 <= len(text) <= 3000:
            excluded += 1
            continue
        family = 'taodescribe-' + digest(' '.join(title.split()).casefold())[:20]
        candidate = {'id': 'taodescribe-' + digest([source_id, text])[:20], 'family': family,
                     'source_id': source_id, 'task': 'item_parse', 'input': {'text': text},
                     'source_title': title, 'content_sha256': digest(text)}
        # Stable hash ordering avoids dependence on input traversal/random module versions.
        rank = digest([seed, family, candidate['id']])
        if family not in candidates or rank < candidates[family][0]:
            candidates[family] = (rank, candidate)
    selected = [row for _, row in sorted(candidates.values(), key=lambda pair: pair[0])[:count]]
    if len(selected) < count:
        raise ValueError(f'Only {len(selected)} eligible distinct products; requested {count}')
    return selected, {'eligible_families': len(candidates), 'excluded_rows': excluded}


def sample_products(*, csv_path, images_root, count, seed):
    root = Path(images_root).resolve()
    candidates, seen = {}, set()
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {'name', 'class'} <= set(reader.fieldnames or []):
            raise ValueError('Products-10K CSV requires name,class (optional group)')
        for row in reader:
            name, sku = (row['name'] or '').strip(), (row['class'] or '').strip()
            p = PurePosixPath(name)
            if not name or not sku or p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:
                raise ValueError('Invalid Products-10K image path or SKU')
            if name in seen:
                raise ValueError('Duplicate image filename in Products-10K index')
            seen.add(name)
            candidate = {'id': 'products10k-' + digest([sku, name])[:20],
                         'family': 'products10k-sku-' + digest(sku)[:20],
                         'source_id': name, 'source_sku': sku, 'source_group': row.get('group'),
                         'task': 'vision_draft'}
            rank = digest([seed, sku, name])
            if sku not in candidates or rank < candidates[sku][0]:
                candidates[sku] = (rank, candidate)
    selected = [row for _, row in sorted(candidates.values(), key=lambda pair: pair[0])[:count]]
    if len(selected) < count:
        raise ValueError(f'Only {len(selected)} distinct SKUs; requested {count}')
    for row in selected:
        path = (root / row['source_id']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Missing or unsafe image: {row["source_id"]}')
        from backend.app.vision import image_data
        from fastapi import HTTPException
        try:
            image_data(path)
        except HTTPException:
            raise ValueError(f'Image exceeds production limits or cannot decode: {row["source_id"]}') from None
        row['content_sha256'] = file_hash(path)
        row['input'] = {'images': [{'path': 'images/' + row['content_sha256'] + path.suffix.lower(),
                                    'sha256': row['content_sha256']}], 'note': ''}
    return selected, {'eligible_families': len(candidates), 'indexed_images': len(seen)}


def write_sample(output, rows, metadata, images_root=None):
    destination = Path(output)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Sample output directory must be empty')
    destination.mkdir(parents=True, exist_ok=True)
    if images_root is not None:
        for row in rows:
            target = destination / row['input']['images'][0]['path']
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(Path(images_root) / row['source_id'], target)
    write_json(destination / 'samples.json', {'metadata': metadata, 'samples': rows})
    write_json(destination / 'annotations.json', {'samples_hash': digest(rows), 'annotations': [
        {'id': row['id'], 'expected': None, 'rationale': '', 'annotator': '',
         'label_status': 'draft', 'split': 'dev', 'enabled': True} for row in rows]})
    return destination


def build_cases(package):
    package = Path(package)
    samples = read_json(package / 'samples.json')
    annotations = read_json(package / 'annotations.json')
    if annotations.get('samples_hash') != digest(samples['samples']):
        raise ValueError('Samples changed after annotation template was created')
    rows = {row['id']: row for row in samples['samples']}
    labels = annotations.get('annotations', [])
    if len(labels) != len(rows) or {label['id'] for label in labels} != set(rows):
        raise ValueError('Annotations must cover every sample exactly once')
    cases = []
    for label in labels:
        row = rows[label['id']]
        if not label.get('expected') or not label.get('rationale') or not label.get('annotator'):
            raise ValueError(f'{row["id"]}: expected, rationale and annotator must be filled before building')
        metadata = samples['metadata']
        case = dict(id=row['id'], task=row['task'], enabled=label['enabled'], split=label['split'],
                    family=row['family'], tags=['public-data', metadata['dataset']],
                    source=f"{metadata['source_url']} | {metadata['source_version']} | {row['source_id']} | sha256:{row['content_sha256']}",
                    rationale=f"{label['rationale']} 标注者：{label['annotator']}。",
                    label_status=label['label_status'], input=row['input'], expected=label['expected'])
        cases.append(Case.model_validate(case).model_dump(mode='json'))
    destination = package / 'cases'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Cases directory must be empty; use a new version for changed annotations')
    destination.mkdir(exist_ok=True)
    for case in cases:
        write_json(destination / (case['id'] + '.json'), case)
    write_json(package / 'build.json', {'samples_hash': digest(samples), 'annotations_hash': digest(annotations),
                                     'case_count': len(cases), 'cases_hash': digest(cases)})
    return cases
