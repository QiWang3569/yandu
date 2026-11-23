# AI pipeline evaluation summary

- dataset version: `2026-11-23-v2`
- dataset verified: `True`
- git sha: `54df454fcb45ef7726bf43f24fffae3d287a157c`
- mode: `real`
- generated at: `2026-11-23T03:31:59.232249+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 1.1 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.1 | sealed_test | field_macro_f1 | 0.842 | min=0.85 | False |
| text-primary | 1.1 | sealed_test | clarification_accuracy | 1.000 | min=0.8 | True |
| text-primary | 1.1 | sealed_test | p95_latency_ms | 5592.450 | max=20000 | True |
| text-primary | 2.1 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.1 | sealed_test | field_macro_f1 | 0.864 | min=0.85 | True |
| text-primary | 2.1 | sealed_test | hard_field_exact | 0.972 | min=0.9 | True |
| text-primary | 2.1 | sealed_test | quote_recall | 0.986 | min=0.95 | True |
| text-primary | 2.1 | sealed_test | injection_structure_rate | 1.000 | min=1.0 | True |
| text-primary | 2.1 | sealed_test | p95_latency_ms | 5378.800 | max=20000 | True |
| text-primary | 2.4 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | sealed_test | verdict_accuracy | 0.667 | min=0.8 | False |
| text-primary | 2.4 | sealed_test | match_recall | 0.769 | min=0.85 | False |
| text-primary | 2.4 | sealed_test | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | sealed_test | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | p95_latency_ms | 5798.900 | max=20000 | True |
| vision-primary | 1.2 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | sealed_test | status_accuracy | 0.889 | min=0.8 | True |
| vision-primary | 1.2 | sealed_test | category_accuracy | 0.889 | min=0.8 | True |
| vision-primary | 1.2 | sealed_test | unsupported_attribute_rate | 0.222 | max=0.05 | False |
| vision-primary | 1.2 | sealed_test | p95_latency_ms | 8009.000 | max=30000 | True |
| program | 2.3 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| program | 2.3 | sealed_test | recall_at_10 | 0.960 | min=0.8 | True |
| program | 2.3 | sealed_test | p95_latency_ms | 16.000 | max=5000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 1.1 | 12 | 12 | 6692 | 1132 | 0 |
| text-primary | 2.1 | 18 | 18 | 20405 | 2360 | 0 |
| text-primary | 2.4 | 18 | 18 | 8122 | 969 | 0 |
| vision-primary | 1.2 | 9 | 9 | 13032 | 1201 | 0 |
| program | 2.3 | 18 | 0 | 0 | 0 | 0 |

## Failure samples

None.
