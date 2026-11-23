# AI pipeline evaluation summary

- dataset version: `2026-11-23-v3`
- dataset verified: `True`
- git sha: `d5b5bb65ebafc5abddaedc4d7d4190986d40b69b`
- mode: `real`
- generated at: `2026-11-23T08:29:59.571310+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-3", "2.1": "intent-3", "2.3": "lexical-alias-1", "2.4": "review-1", "1.4": "concept-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 1.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.1 | dev | field_macro_f1 | 0.867 | min=0.85 | True |
| text-primary | 1.1 | dev | clarification_accuracy | 1.000 | min=0.8 | True |
| text-primary | 1.1 | dev | p95_latency_ms | 1569.500 | max=20000 | True |
| text-primary | 2.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.1 | dev | field_macro_f1 | 0.860 | min=0.85 | True |
| text-primary | 2.1 | dev | hard_field_exact | 1.000 | min=0.9 | True |
| text-primary | 2.1 | dev | quote_recall | 1.000 | min=0.95 | True |
| text-primary | 2.1 | dev | injection_structure_rate | 1.000 | min=1.0 | True |
| text-primary | 2.1 | dev | p95_latency_ms | 6189.000 | max=20000 | True |
| text-primary | 2.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | dev | verdict_accuracy | 0.833 | min=0.8 | True |
| text-primary | 2.4 | dev | match_recall | 1.000 | min=0.85 | True |
| text-primary | 2.4 | dev | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | dev | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | dev | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | dev | p95_latency_ms | 1653.200 | max=20000 | True |
| text-primary | 1.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.4 | dev | schema_valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.4 | dev | accept_accuracy | 1.000 | min=0.8 | True |
| text-primary | 1.4 | dev | family_f1 | 1.000 | min=0.7 | True |
| text-primary | 1.4 | dev | alias_f1 | 0.389 | min=0.7 | False |
| text-primary | 1.4 | dev | evidence_grounded_rate | 1.000 | min=1.0 | True |
| text-primary | 1.4 | dev | p95_latency_ms | 5250.000 | max=20000 | True |
| text-alt | 1.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt | 1.1 | dev | field_macro_f1 | 0.873 | min=0.85 | True |
| text-alt | 1.1 | dev | clarification_accuracy | 1.000 | min=0.8 | True |
| text-alt | 1.1 | dev | p95_latency_ms | 3542.100 | max=20000 | True |
| text-alt | 2.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt | 2.1 | dev | field_macro_f1 | 0.880 | min=0.85 | True |
| text-alt | 2.1 | dev | hard_field_exact | 1.000 | min=0.9 | True |
| text-alt | 2.1 | dev | quote_recall | 1.000 | min=0.95 | True |
| text-alt | 2.1 | dev | injection_structure_rate | 1.000 | min=1.0 | True |
| text-alt | 2.1 | dev | p95_latency_ms | 3918.600 | max=20000 | True |
| text-alt | 2.4 | dev | valid_rate | 0.917 | min=0.98 | False |
| text-alt | 2.4 | dev | verdict_accuracy | 0.667 | min=0.8 | False |
| text-alt | 2.4 | dev | match_recall | 0.667 | min=0.85 | False |
| text-alt | 2.4 | dev | grounding_rate | 1.000 | min=1.0 | True |
| text-alt | 2.4 | dev | exclusion_false_accept | 0 | max=0 | True |
| text-alt | 2.4 | dev | preference_only_reject | 1 | max=0 | False |
| text-alt | 2.4 | dev | p95_latency_ms | 10179.200 | max=20000 | True |
| text-alt | 1.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt | 1.4 | dev | schema_valid_rate | 1.000 | min=0.98 | True |
| text-alt | 1.4 | dev | accept_accuracy | 0.833 | min=0.8 | True |
| text-alt | 1.4 | dev | family_f1 | 0.800 | min=0.7 | True |
| text-alt | 1.4 | dev | alias_f1 | 0.556 | min=0.7 | False |
| text-alt | 1.4 | dev | evidence_grounded_rate | 1.000 | min=1.0 | True |
| text-alt | 1.4 | dev | p95_latency_ms | 3410.000 | max=20000 | True |
| text-alt-2 | 1.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt-2 | 1.1 | dev | field_macro_f1 | 0.848 | min=0.85 | False |
| text-alt-2 | 1.1 | dev | clarification_accuracy | 0.875 | min=0.8 | True |
| text-alt-2 | 1.1 | dev | p95_latency_ms | 31140.150 | max=20000 | False |
| text-alt-2 | 2.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt-2 | 2.1 | dev | field_macro_f1 | 0.870 | min=0.85 | True |
| text-alt-2 | 2.1 | dev | hard_field_exact | 0.979 | min=0.9 | True |
| text-alt-2 | 2.1 | dev | quote_recall | 0.972 | min=0.95 | True |
| text-alt-2 | 2.1 | dev | injection_structure_rate | 1.000 | min=1.0 | True |
| text-alt-2 | 2.1 | dev | p95_latency_ms | 54671.750 | max=20000 | False |
| text-alt-2 | 2.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-alt-2 | 2.4 | dev | verdict_accuracy | 0.833 | min=0.8 | True |
| text-alt-2 | 2.4 | dev | match_recall | 1.000 | min=0.85 | True |
| text-alt-2 | 2.4 | dev | grounding_rate | 1.000 | min=1.0 | True |
| text-alt-2 | 2.4 | dev | exclusion_false_accept | 0 | max=0 | True |
| text-alt-2 | 2.4 | dev | preference_only_reject | 0 | max=0 | True |
| text-alt-2 | 2.4 | dev | p95_latency_ms | 43795.550 | max=20000 | False |
| text-alt-2 | 1.4 | dev | valid_rate | 0.833 | min=0.98 | False |
| text-alt-2 | 1.4 | dev | schema_valid_rate | 0.833 | min=0.98 | False |
| text-alt-2 | 1.4 | dev | accept_accuracy | 0.833 | min=0.8 | True |
| text-alt-2 | 1.4 | dev | family_f1 | 0.800 | min=0.7 | True |
| text-alt-2 | 1.4 | dev | alias_f1 | 0.433 | min=0.7 | False |
| text-alt-2 | 1.4 | dev | evidence_grounded_rate | 0.833 | min=1.0 | False |
| text-alt-2 | 1.4 | dev | p95_latency_ms | 88398.500 | max=20000 | False |
| vision-primary | 1.2 | dev | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | dev | status_accuracy | 1.000 | min=0.8 | True |
| vision-primary | 1.2 | dev | category_accuracy | 1.000 | min=0.8 | True |
| vision-primary | 1.2 | dev | unsupported_attribute_rate | 0.000 | max=0.05 | True |
| vision-primary | 1.2 | dev | p95_latency_ms | 3941.250 | max=30000 | True |
| vision-alt | 1.2 | dev | valid_rate | 1.000 | min=0.98 | True |
| vision-alt | 1.2 | dev | status_accuracy | 0.833 | min=0.8 | True |
| vision-alt | 1.2 | dev | category_accuracy | 1.000 | min=0.8 | True |
| vision-alt | 1.2 | dev | unsupported_attribute_rate | 0.000 | max=0.05 | True |
| vision-alt | 1.2 | dev | p95_latency_ms | 2375.000 | max=30000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 1.1 | 8 | 8 | 4668 | 863 | 0 |
| text-primary | 2.1 | 12 | 12 | 13628 | 1166 | 0 |
| text-primary | 2.4 | 12 | 12 | 5736 | 584 | 0 |
| text-primary | 1.4 | 6 | 6 | 2961 | 392 | 0 |
| text-alt | 1.1 | 8 | 8 | 5420 | 884 | 0 |
| text-alt | 2.1 | 12 | 12 | 14756 | 1548 | 0 |
| text-alt | 2.4 | 12 | 14 | 7901 | 872 | 1 |
| text-alt | 1.4 | 6 | 6 | 3525 | 265 | 0 |
| text-alt-2 | 1.1 | 8 | 8 | 4379 | 4299 | 0 |
| text-alt-2 | 2.1 | 12 | 13 | 12825 | 10325 | 0 |
| text-alt-2 | 2.4 | 12 | 13 | 5457 | 5432 | 0 |
| text-alt-2 | 1.4 | 6 | 11 | 3703 | 5416 | 1 |
| vision-primary | 1.2 | 6 | 6 | 8688 | 656 | 0 |
| vision-alt | 1.2 | 6 | 6 | 7566 | 472 | 0 |

## Failure samples

| candidate | node | sample | error |
|---|---|---|---|
| text-alt | 2.4 | 2.4-003 | ModelUnavailable |
| text-alt-2 | 1.4 | 1.4-002 | ModelUnavailable |
