# V8 bounded real-material acceptance

## What was actually checked

An agent manually inspected **27 fragments in 6 preserved source snapshots**, then recorded independent expected decisions before replaying the production grounding validator and review builder. This was **not an API/model extraction test or independent human adjudication**. Precision and recall are deliberately `null`.

| Preserved material | Documents | Scope |
|---|---:|---|
| EasyOffer interview compilation | 2 | Generic vs personal/project clauses, company contexts, same repository across two files |
| wdndev explicit-question compilation | 1 | Definition vs comparison; compilation is valid evidence |
| wdndev explanatory notes | 1 | Topic heading/answer prose must not become invented questions |
| Previously preserved Maimai excerpts | 2 | Generic questions, splitting independent Transformer/scaling and coding prompts |

Results: **18 retain / 9 exclude**, **17 pending proposals**, one same-question/same-repository evidence merge, **9 baseline-mapped fragments**. Zero approval, new occurrences, model calls or publication. “Exclude” here includes nonquestions as well as personal material; the report is not a classifier's predicted output.

All six documents use unknown interview dates. Repository update dates and month/day filenames do not supply a year. Maimai excerpt filenames are not company evidence: these excerpts alone leave company “其他” and direction “unknown”. Full pages were not fetched. Tencent/ByteDance context is explicit in the preserved interview file headers/paths. Topic tags are not job directions.

## Corrections established from source evidence

The baseline had exactly one record and one file-evidence entry for each of these cards. The original prompts did not ask the extra subquestion:

- `ghv3-003`: remove inferred “why it accelerates”; normalized title/record wording now **介绍大模型投机采样。**
- `ghv3-066`: remove inferred comparison with point-to-point; now **什么是集体通信？**

Stable IDs, evidence links, source pairs, counts and all other record fields are preserved. Golden metadata retains the old/new titles and bound case IDs. These are targeted corrections, not a claim that all 323 cards are semantically audited.

The old Leapmotor `manual-mock-not-api-tested` result bundled independent prompts. Golden expectations now split Transformer principle from attention scaling and split the two coding problems. That historical mock remains historical evidence, not a live extractor benchmark. No production rule can prove semantic question atomicity; a real model response still needs review.

## Reproduction and privacy

The fixture contains document hashes, Unicode-code-point offsets (end exclusive), fragment hashes, brief concept labels and manual decisions. **No source document bodies or verbatim evidence fragments are bundled.** Snapshot hash drift or missing snapshots makes the standalone audit fail; it must never silently download replacements.

```sh
# Standard portable suite: private-source replay tests explicitly SKIP without opt-in.
python -m unittest discover -s tools/collection -p 'test_*.py'

# Full private-source replay; SOURCE_DIR is your preserved research directory.
ALGOWEN_ACCEPTANCE_SOURCES="$SOURCE_DIR" python -m unittest discover -s tools/collection -p test_real_source_acceptance.py
python tools/collection/real_source_acceptance.py --source-root "$SOURCE_DIR"
```

`real_source_acceptance.py`, the metadata fixture and tests are portable. **Do not include the external research snapshots, raw files, manual excerpts, parser trials, or local test output containing source text in a public site/package.** Public site builders should continue copying only their established runtime assets.

## Remaining acceptance, not covered by this pass

- Run a user-authorized real provider request on permitted text and manually compare *predicted* outputs to these expectations. Record omissions, false inclusions, independent-prompt splits and merge errors; don't feed golden labels as if they were predictions.
- Independently adjudicate the golden labels; this is one agent's bounded sample, not statistically representative accuracy.
- Expand to fully evidenced 2022/older dates, explicit multi-role records, multi-company documents and other platforms. This sample does **not** establish real-source coverage for those cases. Existing rule tests are a separate assurance.
- Verify the full page context before assigning company/role to isolated Maimai excerpts. Preserve unknown rather than guessing.
- Continue semantic review of remaining baseline cards; matching hashes/offsets establishes provenance, not faithful paraphrase or source authenticity.
