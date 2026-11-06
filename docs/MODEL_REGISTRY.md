# Declarative model catalog and on-demand execution

Since 0.6.0, `MODEL_LOADING_MODE=on_demand` is the default. Every configured
repository can be selected without `enabled:true`, a local model path
or a validation receipt. The 48 current repository entries are eligible for a
runtime attempt. Selection never downloads or loads weights. The first job
downloads a standard Hugging Face snapshot; subsequent jobs reuse its persistent
cache. The catalog refreshes cache state without restarting the API.

Unsupported/checkpoint/dependency failures affect only that model's batch; valid
outputs from other models are retained, logged and explicitly packaged as partial
results. The instructions below about mandatory preflight, pending-review gates
and disabled formats describe only the optional `validated_local` policy.
See [ON_DEMAND_MODELS.md](ON_DEMAND_MODELS.md) for current loading, label handling,
immutable revision pins, runtime compatibility, errors and network requirements.

`catalog/models.yaml` is the only runtime registry. It contains primary categories,
checkpoint definitions, language applicability and an independent multilingual
section. The browser builds the controls from `/api/models`; adding a category or
checkpoint requires no frontend change. Restart API and worker together after
changing the catalog, and drain the queue before changing checkpoint contracts.

## Inventory and evidence

The correction imports all **36 repository links** from the user-supplied
`HuggingFace NER models list.xlsx`, plus the exact user-specified
[BSC-NLP4BIA/GreekMedNLP-bert-base-greek-uncased-v1-2025-2026](https://huggingface.co/BSC-NLP4BIA/GreekMedNLP-bert-base-greek-uncased-v1-2025-2026).
Spanish, Catalan and Greek entries coexist with English and the DT4H languages.
The previous `es-disease`, `es-symptom` and `en-disease` IDs remain registered.

Spanish categories are Diseases, Symptoms, Medications, Procedures, Anonymization,
Human, Species, Professions, Locations, Negation / Uncertainty and Temporality.
Pediatric Events and Situations are registered for Spanish/Catalan but disabled:
the workbook marks their checkpoint as pending. Temporality is also not released.
Initial experiments without checkpoint links are documented in the provenance
inventory rather than represented as executable checkpoints.

`catalog/inventory-provenance.json` records the workbook SHA-256, original sheet
and cell, repository, dataset and reported metrics. Its metrics are inventory
claims, **not independently reproduced scores**. A shared Chagas cell reports a
combined experiment; those values are not attributed to either checkpoint.
Verified metrics may be explicitly registered under `verified_metrics`, including
their evaluation source/split/method. The public model information exposes these
separately from mere checkpoint availability. Names never receive ranking badges.
The exact combined-corpus Greek card could not be retrieved; no scores have been
copied from its distinct 2026-only sibling.

The independent Multilingual models section includes the ten entries in the
[BSC DT4H multilingual collection](https://huggingface.co/collections/BSC-NLP4BIA/dt4h-multilingual-ner-models)
and the published
[DT4H medication checkpoint](https://huggingface.co/DT4H/cardio-ner-multilingual-medication-xlm-roberta-large-multiclass).
Their declared training languages remain explicit. The section is accessible from
every document language; unsupported language/model combinations are disabled,
not silently routed to a Spanish segmenter. Czech/Swedish use ISO `cs`/`sv`, based
on the public DT4H cards (the workbook uses `CZ`/`SW`). No selection is forced.

## Schema and selection

A category contains `display_name`, optional `description`, and `models`, a list
of stable checkpoint IDs referencing root `models` definitions:

```yaml
languages:
  es:
    display_name: Spanish
    entities:
      LOCATION:
        display_name: Locations
        models: [location-example]
models:
  location-example:
    name: Location detector — version 1
    language: es                 # must match the saved encoding
    languages: [es]              # validated document-language applicability
    target_label: GPE_NOM        # original checkpoint label, never guessed at runtime
    label_mapping: {GPE_NOM: LOCATION}
    task: ner
    requires: []
    schema_review: complete
    enabled: true
    model_dir: /models/location-example-v1
    min_score: 0.0
    batch_size: 16
```

This is a configuration example, not an installed clinical model. A shared
checkpoint can be referenced by several canonical categories; all mapped
categories must be declared. IDs/canonical labels use safe identifiers; repository
IDs such as `BSC-NLP4BIA/location-tagger` identify trusted administrator-configured
Hub sources in on-demand mode; users cannot submit arbitrary repository paths.
In validated-local mode they are descriptive metadata. A root `multilingual.entities` block uses the same
category-reference structure. Supported languages are validated server-side.

Each category expands into individual unchecked model checkboxes. Opening it does
not select any checkpoint. Users can choose several models in the same category
and combine specialized with compatible multilingual checkpoints. The same shared
multilabel checkpoint appears once in the multilingual section and executes once.
Category badges/counts reflect the union of active checkpoints.

New clients submit repeated `models` fields. The server derives the canonical
entity set; any supplied `entities` must agree with the selected checkpoints.
Unknown, duplicated, unavailable or incompatible IDs are rejected before ingestion.
Legacy category-only requests remain compatible with the original single-model
`model_id` fields; ambiguous new categories require explicit checkpoint IDs.

## Original labels and consolidation

Mappings are per checkpoint, not global string aliases: `PROFESION` in an
anonymization checkpoint stays under Anonymization, while a profession model maps
it to Professions. Location subtypes, profession subtypes and negation/uncertainty
labels do not become additional entity-selector checkboxes.

Consolidation keys are `(document, canonical category, start, end)`. One mention
keeps all distinct supporting predictions in `sources` (model ID, version,
original label, individual score), plus `model_ids` and `original_labels`.
The legacy top-level score/model fields represent the highest available score;
ties are deterministic. Scores are not averaged and no model consensus score is
invented. Every different boundary or canonical category remains a separate span,
including nested, crossing and identical-boundary overlaps across categories.

The API/artifact JSON, desktop inspector and mobile detail sheet expose all
sources. BRAT contains one canonical text-bound annotation per consolidated
mention. TSV keeps its original columns and appends JSON-encoded `model_ids`,
`original_labels`, `sources`, and a representative `model_version`; original
sublabels/scores are not discarded. Native statistics count consolidated mentions.

## Tasks and dependencies

`requires` references stable IDs. Startup rejects missing dependencies and cycles;
selection produces a dependency-first order. The microbatch pipeline preserves
that order and passes upstream annotations to a classifier-specific `classify`
method. It never calls an annotation-dependent stage as independent NER.

The legacy native encoder contract is single-target IOB2. Its preflight rejects arbitrary
multi-label schemas, unsupported custom MTL architectures and dependent tasks
without an audited native adapter. The public
[DT4H MTL card](https://huggingface.co/BSC-NLP4BIA/DT4H_XLM-R_mtl_multilingual_multilabel)
explicitly describes a custom multi-head checkpoint. These entries are retained
and disabled under the legacy validated-local policy. On-demand mode attempts
configured sources and records a per-model error for unsupported formats.

[LocationSubTagger](https://huggingface.co/BSC-NLP4BIA/location-sub-tagger)
is registered next to LocationTagger under Locations. Its card describes token
classification and word pre-tokenization, with five role labels. The linked usage
notebook returned 404; a local checkpoint/input contract could not be inspected.
The workbook alone does not establish whether prior detected annotations are
required. Therefore `dependency_review: pending` and a candidate detector are
recorded, without asserting an unverified mandatory dependency. Validated-local
mode blocks it until review and native-adapter validation are complete; default
on-demand mode attempts the configured source. If prior spans are
required, set `requires: [location-tagger]` and provide the audited stage adapter;
otherwise record the reviewed independent input contract. This uncertainty does
not remove the model from the category.

## Optional legacy provision and validation

All imported checkpoints start disabled, with no invented local paths. Review
actual `encoding.json`, label IDs, tokenizer/pre-tokenization, input dependencies
and language applicability before setting `schema_review: complete`. The mapping
for a schema not recoverable from the spreadsheet is a pending candidate, not a
verified label contract. Exact single-target compatible exports can use the
native adapter. Multi-label/custom models need native upstream support/adapters;
enabling a YAML flag alone cannot make them compatible.

Run `python -m scripts.validate_models` in the real NLP environment and identical
model paths/cache mounts used at runtime. Preflight initializes actual local
weights and reconstructs the saved ner_lab encoder offline. Its receipt is keyed
by checkpoint ID and binds the complete-directory SHA-256 to the label/language/
task/dependency contract. Editing a mapping cannot reuse a new-format receipt.
Old `language:entity` receipts are accepted for unchanged legacy single-model
entries. Receipts stay local, administrator-writable only, untracked in Git.

Jobs snapshot checkpoint versions/options, label mappings and dependencies at
admission. Changed contracts fail rather than reuse incompatible publications.
Pre-correction queued jobs retain their original snapshot comparison, tokens and
retention deadlines. No database migration is needed for this correction.

`statistics_model` optionally specifies a local fast reference tokenizer;
otherwise the first selected checkpoint provides it. V3 keeps one running native
statistics accumulator and a bounded job-local inference cache keyed by checkpoint
path/digest/device. Increase MAX_LOADED_MODELS only after RAM/VRAM measurement.
