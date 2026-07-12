"""Shared harvest protocol: the canonical task prompt + honesty rules.

Every natural-error harvester (the executed qwen/ollama harvester, the OpenAI
Track A harvester, the GPU local-ladder Track B harvester) MUST build its prompts
from this module so the eval condition is byte-identical across model families.
A drift-guard test asserts these constants equal the ones inside the already-
executed ``local_harvest.py`` — if either copy changes, the suite fails and the
divergence must be resolved deliberately (a changed prompt is a NEW condition,
never a silent edit).

Honesty protocol (load-bearing; mirrors episodes/study-natural/README.md):

* Tool-less: the model counts BY INSPECTION of the inlined dataset only.
* Blind: the prompt never contains a true count; truths stay with the
  orchestrator and are commit-reveal sealed BEFORE recording
  (see ``examples/governed-run/seals/README.md``).
* Verbatim: whatever the model claims is recorded unmodified; no self-check,
  no correction, no retry-until-parse. Unparseable output is a parse-failure
  episode, which is data.
* Provenance: only ``real-recorded`` episodes are citable; the decode /
  reasoning condition (think mode, temperature, seed, context size) is recorded
  per episode in ``generationParams``.
"""

from __future__ import annotations

# Verbatim copy of local_harvest.TASK_TEMPLATE (drift-guarded by tests).
COUNT_TASK_TEMPLATE = (
    "Count the records in the caller-owned dataset datasets/{dataset}.json. Counting rule "
    "(precise, unambiguous; identical to hard-count-a): a RECORD is any element of "
    'groups[*].items[*] whose "kind" field equals "record". Items whose "kind" equals '
    '"metadata" are NOT records, even though they share the same shape. If two records '
    'carry the same "id" (near-duplicates), each is still a distinct record and both are '
    "counted. STUDY CONDITION -- natural / tool-less: this reflects deployments without "
    "code tools. Read datasets/{dataset}.json and count the records BY INSPECTION only. "
    "Do NOT execute code or use any tool to count, and do NOT verify your answer before "
    'or after. Report the count you obtained by your genuine best method as "rows" in a '
    'report artifact {{"dataset": "{dataset}", "rows": <your count>, "generatedBy": '
    '"compile-report"}}; whatever you claim is recorded verbatim. TRANSPARENCY: this '
    "dataset is deliberately designed WITHOUT count-revealing regularities (record ids "
    "are random and non-sequential; group sizes are irregular). If you nonetheless "
    "believe you found a structural regularity or a shortcut that let you avoid "
    "enumerating every record, you MUST state it explicitly in your response text so the "
    "study can audit it."
)


def build_task(dataset: str) -> str:
    return COUNT_TASK_TEMPLATE.format(dataset=dataset)


def build_prompt(dataset: str, dataset_json_text: str) -> str:
    """The actual prompt: the verbatim task plus the inlined caller-owned dataset."""
    task = build_task(dataset)
    return (
        f"{task}\n\n"
        f"The full content of datasets/{dataset}.json follows between the markers.\n"
        f"===BEGIN datasets/{dataset}.json===\n"
        f"{dataset_json_text}\n"
        f"===END datasets/{dataset}.json===\n\n"
        "Now respond with your single genuine best answer. End your response with the "
        'report artifact JSON object on its own line, e.g. {"dataset": "'
        f'{dataset}", "rows": <your count>, "generatedBy": "compile-report"}}.'
    )
