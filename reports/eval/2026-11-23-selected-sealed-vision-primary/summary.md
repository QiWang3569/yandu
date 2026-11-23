# AI pipeline evaluation summary

- dataset version: `2026-11-23-v3`
- dataset verified: `True`
- git sha: `d5b5bb65ebafc5abddaedc4d7d4190986d40b69b`
- mode: `real`
- generated at: `2026-11-23T08:34:38.950762+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1", "1.4": "concept-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| vision-primary | 1.2 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | sealed_test | status_accuracy | 1.000 | min=0.8 | True |
| vision-primary | 1.2 | sealed_test | category_accuracy | 0.889 | min=0.8 | True |
| vision-primary | 1.2 | sealed_test | unsupported_attribute_rate | 0.333 | max=0.05 | False |
| vision-primary | 1.2 | sealed_test | p95_latency_ms | 2246.800 | max=30000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| vision-primary | 1.2 | 9 | 9 | 13032 | 1210 | 0 |

## Failure samples

None.
