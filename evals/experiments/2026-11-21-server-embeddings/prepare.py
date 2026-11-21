"""Prepare unlabeled server inputs and collect local reference rankings."""
import argparse
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = '202fb75'
previous = HERE.parent / '2026-11-21-local-embeddings/run.py'
spec = importlib.util.spec_from_file_location('bench', previous)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def sets():
    held = bench.read(HERE / 'holdout.json')
    return bench.datasets() + [('holdout', held['items'], held['queries'])]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(mode, model_dir):
    data = sets()
    if mode == 'input':
        output = {n: dict(items=[dict(id=i['id'], text=t) for i,t in zip(items, bench.product_texts(items))],
                          queries=[dict(id=q['id'], text=q['query']) for q in queries])
                  for n,items,queries in data}
        write(ROOT/'test-results/server-embedding-input.json', output)
        return
    if mode == 'float':
        _, rank = bench.vector_ranker('m3e', model_dir)
    else:
        rank = bench.keyword_rank
    with tempfile.TemporaryDirectory() as tmp:
        if mode == 'old':
            payload = subprocess.check_output(['git','archive','--format=zip',OLD,'backend/app'], cwd=ROOT)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                archive.extractall(tmp)
            sys.path.insert(0, str(Path(tmp)/'backend'))
            from app import search
            assert Path(search.__file__).resolve().is_relative_to(Path(tmp).resolve())
        rows = {}
        for name, items, queries in data:
            rows[name] = {q['id']: {'ranked': ids, 'score': score}
                          for q,(ids,score) in zip(queries,rank(items,queries),strict=True)}
        write(HERE / (mode+'.json'), rows)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['input','old','current','float'])
    p.add_argument('--model-dir',type=Path)
    args=p.parse_args()
    run(args.mode,args.model_dir)
