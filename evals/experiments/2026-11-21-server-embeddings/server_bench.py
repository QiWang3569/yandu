"""Run inside the disposable CPU benchmark directory with no server application dependencies."""
import hashlib
import json
import os
import platform
import random
import resource
import time
from pathlib import Path

os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false')
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

here = Path(__file__).resolve().parent
clock = time.perf_counter
start = clock()
settings = ort.SessionOptions()
settings.intra_op_num_threads = settings.inter_op_num_threads = 1
settings.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
session = ort.InferenceSession(str(here/'model.onnx'), settings, providers=['CPUExecutionProvider'])
tokenizer = Tokenizer.from_file(str(here/'tokenizer.json'))
tokenizer.enable_truncation(max_length=512)
tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
load_ms = (clock()-start)*1000


def encode(texts):
    tokens = tokenizer.encode_batch(texts)
    inputs = {'input_ids': np.array([t.ids for t in tokens], dtype=np.int64),
              'attention_mask': np.array([t.attention_mask for t in tokens], dtype=np.int64)}
    vectors = session.run(None, inputs)[0]
    assert vectors.shape == (len(texts), 512) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    return vectors


def search(text, docs):
    scores = docs @ encode([text])[0]
    order = np.argsort(-scores, kind='stable')[:5]
    return order, float(scores[order[0]])


data = json.loads((here/'server-embedding-input.json').read_text(encoding='utf8'))
rows = {}
work = []
indexed = {}
for name, ds in data.items():
    start = clock()
    items = ds['items']
    docs = np.concatenate([encode([i['text'] for i in items[offset:offset+8]]) for offset in range(0,len(items),8)])
    indexed[name] = round((clock()-start)*1000,2)
    rows[name] = {}
    for q in ds['queries']:
        order,score = search(q['text'], docs)
        rows[name][q['id']] = {'ranked':[items[i]['id'] for i in order], 'score':score}
        work.append((q['text'],docs))
timings = []
work *= 3
random.Random(116).shuffle(work)
for text,docs in work:
    start = clock()
    search(text,docs)
    timings.append((clock()-start)*1000)
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
with (here/'model.onnx').open('rb') as stream:
    digest = hashlib.file_digest(stream,'sha256').hexdigest()
meta = dict(onnxruntime=ort.__version__, cpu_threads=1, python=platform.python_version(), numpy=np.__version__,
            model_bytes=(here/'model.onnx').stat().st_size,
            sha256=digest,
            load_ms=round(load_ms,2), index_ms=indexed, timed_queries=len(timings),
            p50_ms=round(float(np.percentile(timings,50)),2), p95_ms=round(float(np.percentile(timings,95)),2),
            peak_rss_mib=round(peak,1))
(here/'server.json').write_text(json.dumps({'runtime':meta,'rows':rows},indent=2)+'\n')
print(json.dumps(meta))
