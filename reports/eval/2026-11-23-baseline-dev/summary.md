# AI pipeline evaluation summary

- dataset version: `2026-11-23-v2`
- dataset verified: `True`
- git sha: `6b0141c2e4b557cadb998d62e05bcd3859758ccf`
- mode: `real`
- generated at: `2026-11-23T02:44:39.568966+00:00`
- prompt versions: `{"1.1": "item-2", "1.2": "vision-publish-2", "2.1": "intent-2", "2.3": "lexical-alias-1", "2.4": "review-1"}`

## Metrics

| candidate | node | split | metric | value | rule | pass |
|---|---|---|---|---:|---|---|
| text-primary | 1.1 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 1.1 | dev | field_macro_f1 | 0.867 | min=0.85 | True |
| text-primary | 1.1 | dev | clarification_accuracy | 1.000 | min=0.8 | True |
| text-primary | 1.1 | dev | p95_latency_ms | 1848.150 | max=20000 | True |
| text-primary | 2.1 | dev | valid_rate | 0.833 | min=0.98 | False |
| text-primary | 2.1 | dev | field_macro_f1 | 0.846 | min=0.85 | False |
| text-primary | 2.1 | dev | hard_field_exact | 0.812 | min=0.9 | False |
| text-primary | 2.1 | dev | quote_recall | 0.000 | min=0.95 | False |
| text-primary | 2.1 | dev | injection_structure_rate | 1.000 | min=1.0 | True |
| text-primary | 2.1 | dev | p95_latency_ms | 11742.650 | max=20000 | True |
| text-primary | 2.4 | dev | valid_rate | 1.000 | min=0.98 | True |
| text-primary | 2.4 | dev | verdict_accuracy | 0.583 | min=0.8 | False |
| text-primary | 2.4 | dev | match_recall | 0.500 | min=0.85 | False |
| text-primary | 2.4 | dev | grounding_rate | 1.000 | min=1.0 | True |
| text-primary | 2.4 | dev | exclusion_false_accept | 0 | max=0 | True |
| text-primary | 2.4 | dev | preference_only_reject | 0 | max=0 | True |
| text-primary | 2.4 | dev | p95_latency_ms | 1326.950 | max=20000 | True |
| vision-primary | 1.2 | dev | valid_rate | 1.000 | min=0.98 | True |
| vision-primary | 1.2 | dev | status_accuracy | 0.833 | min=0.8 | True |
| vision-primary | 1.2 | dev | category_accuracy | 0.667 | min=0.8 | False |
| vision-primary | 1.2 | dev | unsupported_attribute_rate | 0.000 | max=0.05 | True |
| vision-primary | 1.2 | dev | p95_latency_ms | 2015.500 | max=30000 | True |
| program | 2.3 | dev | valid_rate | 1.000 | min=0.98 | True |
| program | 2.3 | dev | recall_at_10 | 0.944 | min=0.8 | True |
| program | 2.3 | dev | p95_latency_ms | 15.450 | max=5000 | True |

## Usage

| candidate | node | samples | calls | input tokens | output tokens | failures |
|---|---|---:|---:|---:|---:|---:|
| text-primary | 1.1 | 8 | 8 | 4668 | 865 | 0 |
| text-primary | 2.1 | 12 | 16 | 10891 | 926 | 2 |
| text-primary | 2.4 | 12 | 12 | 5736 | 603 | 0 |
| vision-primary | 1.2 | 6 | 6 | 8166 | 630 | 0 |
| program | 2.3 | 12 | 0 | 0 | 0 | 0 |

## Failure samples

| candidate | node | sample | error |
|---|---|---|---|
| text-primary | 2.1 | 2.1-002 | HTTPException |
| text-primary | 2.1 | 2.1-003 | HTTPException |
