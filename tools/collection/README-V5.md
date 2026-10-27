# v5 local candidate extraction — NOT deployed

Isolated from v4.1 runtime. No GitHub writes, active workflow, scheduled job,
real API call, key or publication is included. Existing collection and site
runtime are unchanged. `pipeline.py` produces review proposals, never counts,
merges, commits, issues or publishes them.

## Offline / manual test (no dependency or key)

Provide your own UTF-8 text/HTML file and a pre-extracted JSON response matching
`extract.SCHEMA`. This is a mock/manual test, not an LLM accuracy test:

```sh
python tools/collection/pipeline.py --text-file /private/interview.txt \
  --source-url https://example.com/original --mock-response /private/questions.json \
  --output .collection/private-review.json
python -m unittest discover -s tools/collection -v
npm test
```

Use `--html-file` instead for user-supplied HTML. Import is an explicit user
copy/export, never evidence of crawler permission. HTML is parsed locally without
scripts, browsers, image loads, external entities or linked requests. Offsets
refer to normalized extracted text, not HTML byte offsets; `text_sha256` binds
that text. Inputs are bounded (512 KB file; 40,000 extracted characters), not
silently truncated. PDF/OCR and a public web form are **not implemented**.

## Future real provider use — administrator/server only

Install optional `requirements-llm.txt` (exact tested `openai==3.39.0` plus
resolved dependency pins) and set server environment variables:
`OPENAI_API_KEY`, `ALGOTOP_LLM_MODEL` (explicit, no invented default model).
Optionally set `ALGOTOP_LLM_BASE_URL` and, for a custom provider, explicitly
`ALGOTOP_TRUST_CUSTOM_ENDPOINT=yes`. This trusts that provider with the key and
source text; confirm its privacy/security terms first. Ambient OPENAI_BASE_URL
is not used. No API keys belong in browser JS, localStorage, repository files,
command-line arguments, logs, source URLs or artifacts. Use a secret manager or
GitHub Secrets, never paste the key into chat. The future workflow secret name is
`ALGOTOP_OPENAI_API_KEY`. Configure provider account spending limits independently.

Remove `--mock-response` and pass `--allow-llm-content-transfer` only when you
consent to transmitting this document to the configured provider. SDK is lazily
imported. Official `openai.OpenAI(...).chat.completions.create(...)` is used for
OpenAI-compatible APIs. Default `json_schema` is preferred; an explicitly configured
`ALGOTOP_LLM_FORMAT=json_object` supports providers without structured output.
There is no silent downgrade or additional provider switch. Both modes use the
same strict local schema/evidence validator. Unsupported model/parameter errors
fail closed; choose a compatible model, do not assume all providers work.

Bounds: at most 30 questions, question 200 chars, quote 500 chars, response 64,000
chars, default 4,096 output tokens per attempt, two attempts, 30 seconds per
request, 65 seconds start-request budget. SDK internal retries are disabled;
only transient 429/5xx/connection/timeout failures retry. No retries for malformed
JSON, refusal, truncation, schema error or unsupported parameters. Actual token
charges depend on provider; these caps are not a currency-spend guarantee. Error
messages contain constant codes, never provider exceptions or document text.

## Evidence and review

Schema is `{questions:[{question,disposition,evidence:{quote,start,end}}]}`.
Every property is required; extra properties (including company/date claims)
are rejected. `disposition` is `common` or `personal_project_specific`. Quotes
must exactly equal source[start:end], with Python Unicode character offsets,
end exclusive; question text must occur verbatim inside the quote. No fabricated
company/interview/publication dates are emitted. General questions within a
project discussion may be proposed; project-specific details are excluded.

Content is supplied as untrusted data, no model tools are provided. Injection
resistance and exact grounding reduce risk, not prove semantic truth. Human
review must still verify that a question was actually asked, genericness,
2022+ date, role, source authenticity and rights. Exact normalized baseline title
matches map to existing IDs; ambiguous titles/semantic paraphrases require human
mapping. Same canonical GitHub repo plus question is one candidate across files.
All outputs retain pending_human_approval, countEligible=false, zero occurrences
and published=false. No answer generation, invented metadata or auto-promotion.

## URL ingress and WeChat

`--fetch-url URL --policy tools/collection/policy.json` uses existing canonical
URL, current reviewed terms, robots, no-redirect, no-cookie/auth and managed
proxy gates. New body extraction additionally needs an explicit reviewed
`body_extraction_status: permitted` host rule; existing metadata permissions do
not grant body rights. The default managed-proxy path requires `ALGOTOP_TRUSTED_EGRESS=1` and a
trusted enforcing HTTPS proxy; it is not a general SSRF-safe arbitrary proxy.
No current source permission is broadened. A blocked request returns
`needs_manual_content`; use a legitimately obtained user-supplied export, not a
login/captcha bypass or another proxy. No WeChat browser automation, cookie
reuse, paid exporter or unmaintained third-party extraction service is included.

## Integrated weekly runner and GitHub scheduling draft

`run_weekly.py` runs discovery → eligible body fetch → extraction → deduplicated
pending review in one bounded local command. Default is dry-run; network and
LLM text transfer each need explicit flags. At most 3 documents by default (hard
cap 5), 240-second start-request budget (hard cap 300); each model call gets the
remaining budget. Existing metadata-only sources remain blocked for body use.
No source permission is silently expanded, so the current registry can discover
links without producing extracted questions until body permission is approved.

`workflow-drafts/weekly-candidates.yml.disabled` is outside `.github/workflows`,
therefore inert. It describes weekly integrated extraction and optional manual
URL extraction in a **private collector repository**, separate from the public
AlgoTop site. Its job and short-retention candidate artifact upload both require
repository.private; enabling and content-transfer consent are separate variables.
Only pending candidate JSON (short evidence snippets, not original documents) is
uploaded, and only inside that future private repository. Reviewers must still
handle snippets as sensitive. Full bodies, imported attachments and keys are
never artifacts. No repository has been created and no job has been enabled.

For stock GitHub-hosted runners without a managed proxy, explicit
`--direct-public-egress` uses reviewed policy hosts, all-public DNS validation,
a pinned connection IP and verified TLS for the original hostname. It refuses
this direct mode when a configured proxy exists: it is not an egress bypass.
Default local behavior remains the inherited managed-proxy path. Redirects,
private/mixed DNS answers, credential URLs and oversized bodies fail closed.
The 15-second socket timeout is an inactivity timeout, not a strict total
response deadline; OS DNS resolution can also outlast the start-request budget.
The draft job has a 10-minute overall workflow timeout as a final backstop.

Before activation, confirm private repository/deployment scope, source/body
rights and fresh policies, protected environment and reviewer access, provider
and secret setup, review of the included exact dependency lock and action SHA pins. Run actual
provider and hosted-runner smoke tests with explicit authorization and spending
limits. None were run here. The current `.disabled` template is a reviewable
configuration, not a claim of GitHub execution. The static public site has no
API-key backend and remains unchanged; never upload the whole repository.

## Real SDK validation (still no live API test)

The official PyPI `openai==3.39.0` package and its exact resolved dependencies
were installed in an isolated temporary virtualenv. `test_sdk_offline.py` checks
the real SDK request serialization and typed response parsing for both schema
and JSON modes using the SDK's `httpx2.MockTransport`; socket connections are
forbidden and the credential is a clearly nonfunctional fixture string. Client
configuration also confirms ambient OPENAI_BASE_URL cannot override our default.
The optional two tests skip without the SDK installed. Run them with:

```sh
python -m venv /tmp/algotop-sdk-test
/tmp/algotop-sdk-test/bin/pip install -r tools/collection/requirements-llm.txt
/tmp/algotop-sdk-test/bin/python -m unittest discover -s tools/collection -v
```

This proves actual library compatibility, not live model availability, provider
schema acceptance, extraction quality, billing, or GitHub execution. No real key
or API inference was used. HTTP proxy configuration is still honored in normal
production; SOCKS proxy operators may need the SDK's additional SOCKS dependency.
The proxy-free constructor test is isolated and makes no network requests.

The draft uses commit-SHA action pins resolved read-only from official GitHub
`actions/checkout` v4, `actions/setup-python` v5 and `actions/upload-artifact` v4
refs during this validation; it is still outside `.github/workflows` and inert.
Re-review pins before eventual activation rather than silently upgrading them.

Official API references checked for implementation:
- https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat
- https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create
