# AI pipeline evaluation summary

- dataset version: `2026-11-23-v2`
- dataset verified: `True`
- git sha: `54df454fcb45ef7726bf43f24fffae3d287a157c`
- mode: `real`
- generated at: `2026-11-23T03:08:19.557480+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 1.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.1 | dev | field_macro_f1 | 0.879 | min=0.85 | True |
| text-primary | 1.1 | dev | clarification_accuracy | 1.000 | min=0.8 | True |
| text-primary | 1.1 | dev | p95_latency_ms | 1629.350 | max=20000 | True |
| text-primary | 2.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.1 | dev | field_macro_f1 | 0.874 | min=0.85 | True |
| text-primary | 2.1 | dev | hard_field_exact | 0.979 | min=0.9 | True |
| text-primary | 2.1 | dev | quote_recall | 1.000 | min=0.95 | True |
| text-primary | 2.1 | dev | injection_structure_rate | 1.000 | min=1.0 | True |
| text-primary | 2.1 | dev | p95_latency_ms | 6306.250 | max=20000 | True |
| text-primary | 2.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | dev | verdict_accuracy | 0.833 | min=0.8 | True |
| text-primary | 2.4 | dev | match_recall | 1.000 | min=0.85 | True |
| text-primary | 2.4 | dev | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | dev | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | dev | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | dev | p95_latency_ms | 1654.350 | max=20000 | True |
| vision-primary | 1.2 | dev | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | dev | status_accuracy | 1.000 | min=0.8 | True |
| vision-primary | 1.2 | dev | category_accuracy | 1.000 | min=0.8 | True |
| vision-primary | 1.2 | dev | unsupported_attribute_rate | 0.000 | max=0.05 | True |
| vision-primary | 1.2 | dev | p95_latency_ms | 2531.250 | max=30000 | True |
| program | 2.3 | dev | valid_rate | 1.000 | min=0.98 | True |
| program | 2.3 | dev | recall_at_10 | 0.944 | min=0.8 | True |
| program | 2.3 | dev | p95_latency_ms | 16.000 | max=5000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 1.1 | 8 | 8 | 4668 | 867 | 0 |
| text-primary | 2.1 | 12 | 12 | 13582 | 1124 | 0 |
| text-primary | 2.4 | 12 | 12 | 5736 | 589 | 0 |
| vision-primary | 1.2 | 6 | 6 | 8688 | 738 | 0 |
| program | 2.3 | 12 | 0 | 0 | 0 | 0 |

## Failure samples

None.
