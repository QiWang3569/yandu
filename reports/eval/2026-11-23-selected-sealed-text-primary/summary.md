# AI pipeline evaluation summary

- dataset version: `2026-11-23-v3`
- dataset verified: `True`
- git sha: `d5b5bb65ebafc5abddaedc4d7d4190986d40b69b`
- mode: `real`
- generated at: `2026-11-23T08:34:21.038801+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1", "1.4": "concept-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 2.4 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | sealed_test | verdict_accuracy | 0.778 | min=0.8 | False |
| text-primary | 2.4 | sealed_test | match_recall | 0.923 | min=0.85 | True |
| text-primary | 2.4 | sealed_test | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | sealed_test | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | p95_latency_ms | 3076.600 | max=20000 | True |
| text-primary | 1.4 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.4 | sealed_test | schema_valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.4 | sealed_test | accept_accuracy | 0.800 | min=0.8 | True |
| text-primary | 1.4 | sealed_test | family_f1 | 0.750 | min=0.7 | True |
| text-primary | 1.4 | sealed_test | alias_f1 | 0.367 | min=0.7 | False |
| text-primary | 1.4 | sealed_test | evidence_grounded_rate | 1.000 | min=1.0 | True |
| text-primary | 1.4 | sealed_test | p95_latency_ms | 1457.700 | max=20000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 2.4 | 18 | 18 | 8163 | 952 | 0 |
| text-primary | 1.4 | 10 | 10 | 4905 | 737 | 0 |

## Failure samples

None.
