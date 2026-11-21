"""Offline candidate retrieval comparison. Run once per ranker; see README for commands."""
import argparse
import json
import os
import sys
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BENCHMARK = ROOT / 'evals/search_benchmark'
MODELS = {
    'm3e': ('moka-ai/m3e-small', '44c696631b2a8c200220aaaad5f987f096e986df', ''),
    'bge': ('BAAI/bge-small-zh-v1.5', '7999e1d3359715c523056ef9478215996d62a620',
            '为这个句子生成表示以用于检索相关文章：'),
    'mpnet': ('sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
              '4328cf26390c98c5e3c738b4460a05b95f4911f5', ''),
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def datasets():
    catalog = read(BENCHMARK / 'catalog.json')['items']
    cases = [read(p) for p in sorted((BENCHMARK / 'cases').glob('*.json'))]
    queries = [dict(id=c['id'], query=c['input']['text'], group='原有回归',
                    gold=c['expected']['relevant_item_ids'])
               for c in cases if c['enabled'] and c['expected']['retrieval_applicable']]
    focus = read(HERE / 'diagnostics.json')
    extra = [dict(**item, tags=[], price_cents=10000, condition_grade='9成新',
                  campus='燕园校本部', status='ACTIVE', created_at=f'2026-02-01T00:00:{i:02d}')
             for i, item in enumerate(focus['items'])]
    return [('original', catalog, queries), ('diagnostic', catalog + extra, focus['queries'])]


def keyword_rank(items, queries):
    sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
    from app.search import execute_smart_search
    from evals.search_eval import SearchContext
    context = SearchContext({'items': items})
    settings = SimpleNamespace(ai_mode='local', demo_mode=True)
    try:
        rows = []
        for case in queries:
            _, matches, _ = execute_smart_search(context.session, case['query'], settings, size=len(items))
            rows.append(([item.id for item, _ in matches], None))
        return rows
    finally:
        context.close()


def product_texts(items):
    return [' '.join([item['title'], item['description'], *item['tags']]) for item in items]


def top_ids(items, scores):
    import numpy as np
    assert np.isfinite(scores).all()
    rankings = []
    for row in scores:
        order = np.argsort(-row, kind='stable')[:5]
        rankings.append(([items[i]['id'] for i in order], float(row[order[0]])))
    return rankings


def lexical_rank(items, queries):
    from sklearn.feature_extraction.text import TfidfVectorizer
    encoder = TfidfVectorizer(analyzer='char', ngram_range=(1, 2))
    docs = encoder.fit_transform(product_texts(items))
    queries_matrix = encoder.transform([case['query'] for case in queries])
    return top_ids(items, (queries_matrix @ docs.T).toarray())


def vector_ranker(name, model_dir):
    os.environ['HF_HUB_OFFLINE'] = '1'
    import numpy as np
    import torch
    import sentence_transformers as st
    from importlib.metadata import version
    repo, revision, prefix = MODELS[name]
    torch.set_num_threads(4)
    model = st.SentenceTransformer(str(model_dir) if model_dir else repo, revision=revision,
                                   device='cpu', local_files_only=True)
    metadata = dict(model=repo, revision=revision, dimensions=model.get_sentence_embedding_dimension(),
                    query_prefix=prefix, device='cpu', torch=str(torch.__version__),
                    sentence_transformers=version('sentence-transformers'), numpy=np.__version__)
    def rank(items, queries):
        documents = product_texts(items)
        inputs = [prefix + case['query'] for case in queries]
        def encode(texts):
            return model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        scores = encode(inputs) @ encode(documents).T
        return top_ids(items, scores)
    return metadata, rank


def summarize(rows):
    positive = [r for r in rows if r['gold']]
    empty = [r for r in rows if not r['gold']]
    def correct(r, k):
        return set(r['ranked'][:k]).intersection(r['gold'])
    return dict(positive=len(positive), top1=sum(bool(correct(r, 1)) for r in positive),
                hit3=sum(bool(correct(r, 3)) for r in positive),
                recall5=mean(len(correct(r, 5))/len(r['gold']) for r in positive),
                extra3=sum(len(r['ranked'][:3])-len(correct(r, 3)) for r in positive),
                missing3=sum(len(r['gold'])-len(correct(r, 3)) for r in positive),
                empty=len(empty), correctly_empty=sum(not r['ranked'] for r in empty))


def gated_top1(rows, threshold):
    positive = [r for r in rows if r['gold']]
    negative = [r for r in rows if not r['gold']]
    correct = sum(r['top_score'] >= threshold and r['ranked'][0] in r['gold'] for r in positive)
    abstain = sum(r['top_score'] < threshold for r in negative)
    return dict(top1_correct=correct, positive_rejected=sum(r['top_score'] < threshold for r in positive),
                empty_correct=abstain, balanced=(correct/len(positive) + abstain/len(negative))/2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('ranker', choices=['local', 'tfidf', *MODELS])
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    if args.ranker == 'local':
        meta, rank = {'model': 'local-rules'}, keyword_rank
    elif args.ranker == 'tfidf':
        meta, rank = {'model': 'TF-IDF', 'character_ngrams': [1, 2]}, lexical_rank
    else:
        meta, rank = vector_ranker(args.ranker, args.model_dir)
    result = {'config': meta, 'datasets': {}}
    for name, items, cases in datasets():
        titles = {i['id']: i['title'] for i in items}
        assert len(titles) == len(items)
        assert all(set(c['gold']) <= titles.keys() for c in cases)
        rankings = rank(items, cases)
        rows = [dict(**c, ranked=ids[:5], top_score=score, top_titles=[titles[i] for i in ids[:5]],
                     expected_titles=[titles[i] for i in c['gold']])
                for c, (ids, score) in zip(cases, rankings, strict=True)]
        summary = summarize(rows)
        result['datasets'][name] = dict(catalog_size=len(items), summary=summary, records=rows)
        print(name, summary, flush=True)
    if args.ranker != 'local':
        original = result['datasets']['original']['records']
        candidates = sorted({r['top_score'] for r in original} | {1.000001})
        threshold = max(candidates, key=lambda t: gated_top1(original, t)['balanced'])
        result['calibration'] = dict(threshold=threshold, fitted_on='original',
                                     diagnostic=gated_top1(result['datasets']['diagnostic']['records'], threshold))
    target = HERE / (args.ranker + '.json')
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
