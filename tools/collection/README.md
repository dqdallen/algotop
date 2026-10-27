# Manual multi-source candidate collection (v4)

This is a **source-discovery queue**, not approved interview data. It does not
modify `data.json`, question frequencies, answers or `_site`. No scheduler,
GitHub workflow, external LLM, credentials or publishing action is installed.

## Run

```sh
python tools/collection/collect.py --dry-run --output .collection/plan.json
python tools/collection/collect.py --network --max-requests 6 --max-seconds 120 \
  --checkpoint .collection/checkpoint.json --output .collection/run.json
(cd tools/collection && python -m unittest discover -v)
npm test
```

Offline is the default. `--network` is explicit and still respects a current
source-specific permission policy and robots. The existing `ingest.py` offline
import/metadata CLI remains available; its network transport now also requires
the managed proxy and fails closed without it. Checkpoints contain only metadata and
candidate links, not feed summaries or article bodies. Use one writer per
checkpoint; replacement is atomic. Same source/config/policy/day reuses success
without network. A new day rechecks permission and robots, fetching new content.
Failed sources remain retryable on the next manual invocation; there is no
unbounded retry loop. Source IDs and URL hashes are deterministic.

## Actual support and permission

* `rss` and `atom`: parses both RSS and namespaced Atom (including Atom served as
  `application/rss+xml`), dates are **publication claims**, not interview dates.
  Does not fetch enclosures, linked articles or pagination.
* `html`: discovers anchor links from a specific approved public page, no browser,
  JS, account or recursive crawling. Does not infer questions from navigation.
* `github_readme`: discovers explicit Markdown HTTPS links from approved raw
  README URLs. This is **not** a GitHub search API/crawler. Canonical repository
  identity normalizes `owner/repo`; multiple files never imply multiple repos.
* `sources.json` includes Nowcoder/blogs/CSDN/GitHub candidates and explicitly
  pending Zhihu/Maimai/Bilibili/WeChat/Xiaohongshu entries. Each original entry
  references an unchanged index of `platform-access.json`. Readable via a web
  tool is not crawler permission or verified original-interview evidence.
* The two exact CNblogs feeds and one CSDN feed are permitted for metadata
  discovery based on publisher RSS invitations; their linked articles are not
  permitted. The exact Zhang Zhao article advertises CC BY 4.0 and is permitted
  for metadata/link discovery with original attribution. Every other source is
  closed/pending until its specific permission is reviewed. No claim that an entire platform is blocked.

Permissions expire after 30 days, so subsequent scheduled/manual runs must not
silently refresh `reviewed_at`. Exact feed allowlists reject query variations and
sibling paths. Robots are rechecked for each uncached host/run. 401/403/429 pause
the host. Redirects are not followed, no cookie jar or target authentication is
used, and DTD/entity-bearing XML is rejected. The collector respects the existing
managed HTTPS proxy; it does **not** disable environmental egress controls.
Both CLIs fail closed if HTTPS proxy configuration is missing or NO_PROXY would
bypass it. No direct-DNS fallback is used. URLs
must be credential-free HTTPS public-looking domains and reviewed policy hosts.

Limits: serial; at most 100 sources, 100 HTTP requests, 512 KB per response,
15-second per-request timeout, 600-second configured start-request budget,
1,000 candidates per source, and at least 2 seconds between requests. Defaults
are substantially smaller. An in-flight request may finish after the start
budget (at most its request timeout); no new request starts after budget expiry.
Feed descriptions/body text are used only in transient parser memory and are not
written. This parser deliberately does not extract or approve question text.

## Output and approval boundary

`runs` distinguishes dry-run / pending / policy-blocked / robots-blocked /
HTTP failure / fetched-unverified / checkpoint-reused. `source_candidates`
(`candidates` is a compatibility alias) contains discovered links, title,
publication claim, canonical source, content hash and provenance.
`question_candidates` is explicitly empty: feed-item count is **not** a question
count. `metrics.verified_common_questions` and `independent_interview_count` remain
zero. A successful feed proves only source discovery.

Before any question is promoted, a human must verify the original page or
user-provided export, algorithm role and 2022+ interview date, whether a question
was actually asked, exclude personal project-specific details, map generic
questions to the existing taxonomy, and deduplicate occurrences per interview
(or canonical repository for GitHub compilations). No auto-approval or publication
path is provided. Review can retain a generic question within a project follow-up
while excluding the candidate's private implementation choices.

`.collection` outputs are local working evidence, excluded by the existing
allowlist-only site build. Do not upload this whole repository as the live site.

## Reviewer-produced question proposals (weekly handoff)

The discovery CLI is not automatic semantic question extraction. A human or the
weekly research agent reads permitted originals/user-provided exports and writes
brief **paraphrased** proposals with `source_url`, `question`, `disposition`
(`common` versus `personal_project_specific`), `evidence_locator`, `reviewer`,
optional `canonical_question_id`, `interview_date_claim`, and `provenance_claim`.
Then run:

```sh
python tools/collection/review.py tools/collection/review-example-input.json \
  --baseline data.json --output .collection/review-proposals.json
```

This validates required evidence, excludes non-common questions, checks existing
question IDs, deduplicates question/source pairs (GitHub across files is one
repository), and flags a source/question pair already present in the baseline.
Every result remains `pending_human_approval`, `countEligible=false`, zero added
occurrences. It **cannot** approve, merge into runtime, or publish. Proposal input
is reviewer work, not trustworthy proof merely because fields are present.
The example uses historical `platform-access.json` notes (not newly extracted
live questions): two proposed mappings to existing LoRA/RoPE cards and one rejected
personal-project question. Mapping to an existing card is distinct from proving
the same source occurrence was already included.

HTML registry seeds now use explicit title relevance terms; unrelated navigation
is excluded, while the relevant seed page itself is retained. This is only a
source-level heuristic, not an algorithm-role or common-question verifier.

Canonical feed endpoints are recorded separately from publisher subscription
links. CNblogs published HTTP redirects are not followed: exact HTTPS feed
endpoints are tried independently, with their own robots gate. `robots_blocked`
there must remain blocked even if ordinary browsers/feed readers can read them.
CSDN's canonical publisher feed is `rss.csdn.net`, not the original redirecting
`blog.csdn.net` subscription link. Never widen its exact-path permission.

## v4.1: exact public GitHub REST and Nowcoder sitemap discovery

Two more adapters are implemented and fixture-tested:

* `github_contents`: only root-directory JSON metadata for the three existing
  public repositories `jingtian11/EasyOffer`, `km1994/LLMs_interview_notes`, and
  `wdndev/llm_interview_note`. Official [GET repository contents documentation](https://docs.github.com/en/rest/repos/contents#get-repository-content)
  permits unauthenticated requests for public resources. The [rate-limit documentation](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
  specifies the unauthenticated shared-IP limit. Only exact API paths are allowed;
  no recursive directories, base64 file text, README bodies, auth or search API.
  File/directory URLs must belong to the requested canonical repository. All
  discovered files in a repository share one canonical source identity.
* `sitemap`: parses one XML document per explicitly registered source; accepts
  namespace-qualified `urlset` and `sitemapindex`. Nowcoder's own robots file
  advertises `/sitemap.xml` and `/sitemap/subject/sitemap.xml`; permission is scoped
  **only to these two index documents**, not to article crawling or hidden APIs.
  XML `<sitemap>` entries are labeled `sitemap_index_link`; `<url>` entries
  retain `sitemap_url`, even when their URLs appear to point to more sitemap
  documents. URL suffixes never override the XML entry kind. Neither is verified
  interview article evidence.
  Child sitemap links are queued but never automatically traversed. `lastmod`
  is stored as `last_modified_claim`, with `publication_date_claim=null`; it is
  never treated as a publication or interview date.

Both still require robots permission, current exact-path policy, managed HTTPS
proxy, response-size/request caps, no redirects, and candidate-only review.
The original Nowcoder article seeds and raw GitHub README seed remain blocked
unless separately reviewed; these adapters do not silently broaden their scope.
Live success/failure must be read from a fresh run report, not inferred from
these implemented adapters or prior tool/browser access.
