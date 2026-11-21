"""Score frozen rankings after inference. Only this step uses the relevance labels."""
import json
import subprocess
from pathlib import Path
from prepare import HERE, ROOT, OLD, bench, sets, write


def metrics(rows):
    positive = [r for r in rows if r['gold']]
    empty = [r for r in rows if not r['gold']]
    correct = lambda r,k: bool(set(r['gold']).intersection(r['ranked'][:k]))
    return dict(n=len(rows), positive=len(positive), hit1=sum(correct(r,1) for r in positive),
                hit3=sum(correct(r,3) for r in positive), empty=len(empty),
                empty_ok=sum(not r['ranked'] for r in empty),
                set_exact=sum(set(r['ranked'])==set(r['gold']) for r in rows))


if __name__ == '__main__':
    data={k:bench.read(HERE/(k+'.json')) for k in ['old','current','float']}
    remote=bench.read(HERE/'server.json')
    data['int8']=remote['rows']
    prior=HERE.parent/'2026-11-21-local-embeddings/m3e.json'
    threshold=bench.read(prior)['calibration']['threshold']
    summary={'runtime': remote['runtime'], 'threshold_from_previous_run':threshold, 'sets':{}, 'examples':[]}
    for name,items,queries in sets():
        titles={i['id']:i['title'] for i in items}
        by_method={k:[] for k in [*data,'fallback']}
        for q in queries:
            ranks={k:v[name][q['id']]['ranked'] for k,v in data.items()}
            score=data['int8'][name][q['id']]['score']
            ranks['fallback']=ranks['current'] or (ranks['int8'][:1] if score>=threshold else [])
            for k,v in ranks.items():
                assert len(set(v))==len(v) and set(v)<=titles.keys()
                by_method[k].append(dict(**q,ranked=v))
            if name=='holdout':
                summary['examples'].append(dict(query=q['query'],group=q['group'],expected=[titles[i] for i in q['gold']],
                    top3={k:[titles[i] for i in v[:3]] for k,v in ranks.items()}))
        summary['sets'][name]={k:metrics(rows) for k,rows in by_method.items()}
        if name=='original':
            prefix='evals/search_benchmark/cases/'
            paths=subprocess.check_output(['git','ls-tree','-r','--name-only',OLD,'--',prefix],cwd=ROOT,text=True).splitlines()
            unchanged=set()
            for path in paths:
                historical=json.loads(subprocess.check_output(['git','show',f'{OLD}:{path}'],cwd=ROOT))
                if (ROOT/path).exists() and historical==bench.read(ROOT/path):
                    unchanged.add(historical['id'])
            summary['unchanged_original']={k:metrics([r for r in rows if r['id'] in unchanged])
                                           for k,rows in by_method.items()}
        if name=='holdout':
            summary['holdout_by_wording']={k:{g:metrics([r for r in rows if r['group']==g]) for g in ['直接','口语','无货']}
                                           for k,rows in by_method.items()}
    write(HERE/'summary.json',summary)
    print(json.dumps(summary['sets'],indent=1))
