import json
from pathlib import Path
import subprocess
import sys

from evals.reporting import compare_runs
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_process_workers_preserve_case_model_repeat_identity(tmp_path):
    common=[sys.executable,str(ROOT/'scripts/run_model_eval.py'),'run','--cases',str(ROOT/'evals/search_benchmark/cases'),
        '--model-config',str(ROOT/'evals/models.search.json'),'--models','local-rules,oracle',
        '--case-ids','search-core-01,search-ood-01','--repeats','2']
    runs=[]
    for concurrency in (1,2):
        destination=tmp_path/str(concurrency)
        p=subprocess.run([*common,'--concurrency',str(concurrency),'--output',str(destination)],
            cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=45)
        assert p.returncode==0,p.stderr
        manifest=json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
        assert manifest['complete'] and manifest['concurrency']==concurrency and manifest['completed_records']==8
        rows=[json.loads(line) for line in (destination/'records.jsonl').read_text(encoding='utf-8').splitlines()]
        runs.append({(r['case_id'],r['model'],r['repeat']):(r['output'],r['score']) for r in rows})
        assert len(runs[-1])==8
    assert runs[0]==runs[1]
    with pytest.raises(ValueError,match='concurrency'):
        compare_runs(tmp_path/'1',tmp_path/'2',tmp_path/'comparison')
