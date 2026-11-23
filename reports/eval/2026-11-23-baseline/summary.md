# AI pipeline evaluation summary

- dataset version: `2026-11-23-v2`
- dataset verified: `True`
- git sha: `54df454fcb45ef7726bf43f24fffae3d287a157c`
- mode: `real`
- generated at: `2026-11-23T02:48:57.510721+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-2", "2.1": "intent-2", "2.3": "lexical-alias-1", "2.4": "review-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 1.1 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.1 | sealed_test | field_macro_f1 | 0.865 | min=0.85 | True |
| text-primary | 1.1 | sealed_test | clarification_accuracy | 0.917 | min=0.8 | True |
| text-primary | 1.1 | sealed_test | p95_latency_ms | 1739.150 | max=20000 | True |
| text-primary | 2.1 | sealed_test | valid_rate | 0.944 | min=0.98 | False |
| text-primary | 2.1 | sealed_test | field_macro_f1 | 0.821 | min=0.85 | False |
| text-primary | 2.1 | sealed_test | hard_field_exact | 0.931 | min=0.9 | True |
| text-primary | 2.1 | sealed_test | quote_recall | 0.000 | min=0.95 | False |
| text-primary | 2.1 | sealed_test | injection_structure_rate | 1.000 | min=1.0 | True |
| text-primary | 2.1 | sealed_test | p95_latency_ms | 8829.550 | max=20000 | True |
| text-primary | 2.4 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | sealed_test | verdict_accuracy | 0.556 | min=0.8 | False |
| text-primary | 2.4 | sealed_test | match_recall | 0.615 | min=0.85 | False |
| text-primary | 2.4 | sealed_test | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | sealed_test | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | sealed_test | p95_latency_ms | 1792.300 | max=20000 | True |
| vision-primary | 1.2 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | sealed_test | status_accuracy | 0.667 | min=0.8 | False |
| vision-primary | 1.2 | sealed_test | category_accuracy | 0.667 | min=0.8 | False |
| vision-primary | 1.2 | sealed_test | unsupported_attribute_rate | 0.222 | max=0.05 | False |
| vision-primary | 1.2 | sealed_test | p95_latency_ms | 3834.600 | max=30000 | True |
| program | 2.3 | sealed_test | valid_rate | 1.000 | min=0.98 | True |
| program | 2.3 | sealed_test | recall_at_10 | 0.960 | min=0.8 | True |
| program | 2.3 | sealed_test | p95_latency_ms | 16.000 | max=5000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 1.1 | 12 | 12 | 6968 | 1198 | 0 |
| text-primary | 2.1 | 18 | 20 | 13553 | 1156 | 1 |
| text-primary | 2.4 | 18 | 18 | 8559 | 951 | 0 |
| vision-primary | 1.2 | 9 | 9 | 12249 | 1071 | 0 |
| program | 2.3 | 18 | 0 | 0 | 0 | 0 |

## Failure samples

| candidate | node | sample | error |
|---|---|---|---|
| text-primary | 2.1 | 2.1-014 | HTTPException |
