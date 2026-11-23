# AI pipeline evaluation summary

- dataset version: `2026-11-23-v3`
- dataset verified: `True`
- git sha: `d5b5bb65ebafc5abddaedc4d7d4190986d40b69b`
- mode: `real`
- generated at: `2026-11-23T08:33:24.814545+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1", "1.4": "concept-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-alt | 1.1 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-alt | 1.1 | sealed_test | field_macro_f1 | 0.881 | min=0.85 | True |
| text-alt | 1.1 | sealed_test | clarification_accuracy | 1.000 | min=0.8 | True |
| text-alt | 1.1 | sealed_test | p95_latency_ms | 3334.750 | max=20000 | True |
| text-alt | 2.1 | sealed_test | valid_rate | 0.944 | min=0.98 | False |
| text-alt | 2.1 | sealed_test | field_macro_f1 | 0.864 | min=0.85 | True |
| text-alt | 2.1 | sealed_test | hard_field_exact | 0.917 | min=0.9 | True |
| text-alt | 2.1 | sealed_test | quote_recall | 0.931 | min=0.95 | False |
| text-alt | 2.1 | sealed_test | injection_structure_rate | 1.000 | min=1.0 | True |
| text-alt | 2.1 | sealed_test | p95_latency_ms | 5076.300 | max=20000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-alt | 1.1 | 12 | 12 | 8096 | 1182 | 0 |
| text-alt | 2.1 | 18 | 20 | 24557 | 2125 | 1 |

## Failure samples

| candidate | node | sample | error |
|---|---|---|---|
| text-alt | 2.1 | 2.1-004 | HTTPException |
