# Adaptive Provider Portfolio Design

**Status:** Proposed v1 based on official documentation reviewed 2026-07-10. Provider enablement remains benchmark-gated.

**Parent design:** [Adaptive Scientific Research Harness](2026-07-10-adaptive-scientific-research-harness-design.md)

## 1. Decision

The installed providers are a verified baseline, not a permanent product boundary. The harness uses a versioned capability registry so a new provider can be evaluated, enabled, disabled, or retired without changing canonical state, quota, evidence, or delivery logic.

Do not build a fixed Google-plus-Brave or multi-provider fan-out. Select one primary scout. Escalate to another index family only when the first route leaves a named load-bearing gap, when a High contract pre-authorizes parallel coverage, or when provider health makes the primary route unusable.

The best current portfolio is:

1. **Direct source-of-record access:** prefer official repository, package, standards, vulnerability, product, and registry APIs when the query maps to one; these usually beat another search call on authority, structure, and token cost.
2. **Generic independent search:** add Brave first.
3. **Scholarly discovery and identifier verification:** add OpenAlex and Crossref; add Europe PMC for biomedical intent.
4. **Second independent general index:** benchmark Exa against Mojeek and enable the winner by query class rather than by global preference.
5. **Fetch/extract fallback:** keep host fetch first; benchmark Jina Reader for ordinary extraction failures and Firecrawl for JavaScript/PDF failures.
6. **Deep investigation:** retain the existing Perplexity, OpenAI, and Gemini branches; evaluate Exa Deep or Linkup Research only as investigation tools, never as automatic source independence.

## 2. Why Google Plus Brave Is Not the Default

Google Custom Search JSON API is closed to new customers and scheduled for discontinuation on 2027-01-01. It is not a viable new raw-search dependency. [Google lifecycle and pricing](https://developers.google.com/custom-search/v1/overview)

Google coverage remains available through Gemini Grounding with Google Search or a Google SERP wrapper. Those are different products:

- Gemini grounding is a model-mediated search tool with token cost and provider-selected internal queries, not a raw ranked result API. [Gemini grounding](https://ai.google.dev/gemini-api/docs/google-search)
- Serper exposes Google SERP results and therefore belongs to the `google` index family; it does not add independent-index corroboration. [Serper](https://serper.dev/)

Brave exposes its own crawler, index, ranked URLs, snippets, controls, and predictable request pricing. It is the highest-value first addition for cross-index challenge. [Brave Search API](https://brave.com/search/api/)

Default concurrent Google-origin plus Brave calls waste money and context on ordinary questions. They are justified only when:

- the contract is High and latency favors pre-authorized parallelism;
- freshness, region, language, or long-tail coverage is load-bearing;
- the first route produces no acceptable source-of-record candidate;
- top results are concentrated in one publisher or duplicate cluster;
- the first route returns only secondary or model-synthesized evidence;
- retained benchmark evidence predicts material unique-origin gain.

Medium uses sequential escalation because the first result can sharpen the second query. High may run two index families concurrently only when the card names both routes, both physical ceilings, and the expected discriminating value.

## 3. Provider Classification

| Provider | Capability class | Origin class | Portfolio decision |
|---|---|---|---|
| Host WebSearch/fetch | scout, verifier, fetch | host-opaque | retain; track observability limitation |
| Official domain APIs | source-of-record lookup, identifier/version verification | direct registry or publisher | add by actual development query class; not a generic scout |
| Brave Search | scout, verifier | independent index | add first |
| Exa Search/Contents | semantic scout, verifier, fetch | independent index | benchmark against Brave/Mojeek; highlights are context-efficient |
| Mojeek Search | verifier, alternate scout | independent index | benchmark for High; procurement is contact-led |
| OpenAlex | scholarly scout, graph expansion | scholarly index | add |
| Crossref | DOI metadata source of record | scholarly registry | add |
| Europe PMC | biomedical scout/full text | scholarly index | add behind biomedical routing |
| Semantic Scholar | scholarly scout | scholarly index | retain |
| Perplexity Sonar | compressed scout/challenge | aggregated/undisclosed | retain; not an independence vote by itself |
| Perplexity/OpenAI/Gemini Deep Research | investigation | model-mediated retrieval | retain; candidate evidence only |
| Jina Reader | fetch/extract fallback | no discovery independence | benchmark on host-fetch failures |
| Firecrawl | JS/PDF fetch fallback | no discovery independence | enable only for measured failure classes |
| Parallel Search/Extract | context-efficient search/fetch | origin undisclosed | targeted benchmark; do not count as independent family |
| Tavily | search/extract convenience | hybrid/opaque | defer as generic independence provider |
| Linkup | search/research convenience | hybrid/opaque | targeted benchmark only |
| Kagi Search | privacy/quality search | general origin undisclosed | defer pending provenance and API maturity |
| Anthropic Web Search | host/model grounding | origin undisclosed | use when Claude host needs it; no independent vote |
| Serper | Google SERP | Google wrapper | reject as independence provider |
| Bing Search API | retired raw search | unavailable | reject |
| Grounding with Bing | Azure agent grounding | Bing model wrapper | defer for host-neutral core |
| Google Custom Search JSON API | raw search | Google | reject for new deployments due sunset |
| Common Crawl | historical verifier | archive/snapshot | optional historical tool, not live scout |

Current official price observations include Brave Search at $5 per 1,000 requests, Exa Search at $7 per 1,000 requests, OpenAlex search at $1 per 1,000 calls after its daily free allowance, and Crossref public/polite access without a per-call fee. Prices are metadata with a verification date, not constants in routing code. [Brave pricing](https://brave.com/search/api/), [Exa pricing](https://exa.ai/pricing), [OpenAlex pricing](https://developers.openalex.org/api-reference/authentication), [Crossref access](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)

For development research, high-value direct candidates include GitHub repository/release metadata, package registries, OSV or NVD vulnerability records, and IETF standards metadata. They are enabled only for a recognized domain intent and never treated as broad-web coverage. [GitHub REST API](https://docs.github.com/en/rest), [PyPI JSON API](https://docs.pypi.org/api/json/), [OSV API](https://google.github.io/osv.dev/api/), [NVD APIs](https://nvd.nist.gov/developers/vulnerabilities), [IETF Datatracker API](https://datatracker.ietf.org/api/)

## 4. Capability Registry

The registry describes capabilities and constraints. Its record order never implies routing preference.

Required provider fields:

```text
id
adapter
adapter_version
enabled
roles
action_categories
stage_capabilities
request_multiplicity
execution_binding
adoption_status
adoption_evidence
index_family
index_provenance
upstream_provider
retrieval_shape
evidence_capabilities
controls
metering
transport
privacy
storage_rights
lifecycle
required_env
docs_url
docs_verified_at
```

`index_provenance` is one of:

- `independent`
- `scholarly-index`
- `registry`
- `hybrid-opaque`
- `wrapper`
- `grounding-wrapper`
- `fetch-only`
- `archive`
- `unknown`

Unknown facts are typed as `unknown`, `not_disclosed`, `not_applicable`, or `not_tested`; they are not omitted.

`request_multiplicity` maps each supported action category to the exact physical research requests issued by one logical invocation. Ordinary routes declare `1`; a composite route such as `cascade` declares its full expansion. The contract records both `invocations` and physical `count`, and quota enforcement uses the latter.

Every canonical session snapshots the full resolved registry hash, exact records for routes referenced by its confirmed contract, and a separately recomputable referenced-records hash. A later registry update cannot rewrite historical route meaning, and historical validation does not falsely claim that a partial record snapshot can reproduce the full-registry hash.

The confirmation object binds the normalized contract-card hash, full resolved registry hash, and referenced-records hash. An overlay applied after confirmation is acceptable only when all three hashes still match; otherwise the card must be regenerated and reconfirmed.

An adapter is executable only when:

- its registry record is valid and `enabled=true`;
- the adapter implementation and exact version exist and every outbound path is bound to the common v2 request interceptor;
- required keys or keyless capability pass preflight;
- lifecycle has no active sunset blocker;
- contract privacy and retention are compatible with provider policy;
- the requested operation fits the declared stage and action category.
- `adoption_status` and a retained evidence reference authorize the requested query class.

An overlay may add a disabled candidate or monotonically restrict an existing route. For a committed enabled route it may disable, remove capabilities, tighten privacy/retention, or lower operational ceilings; it cannot change adapter/version, multiplicity, execution binding, index/upstream identity, grant broader storage rights, or add execution capability. It cannot turn `unbound`, `not_tested`, or missing-adapter metadata into an executable provider merely by setting `enabled=true`. Broader changes require a reviewed committed registry update, adapter fixtures, and re-confirmation. Credential readiness and legacy CLI availability are diagnostics, not execution binding or adoption evidence.

`execution_binding` distinguishes `v2_request_boundary`, `host_native_observed`, `local`, `no_network_demo`, and unbound states. Only the first may enable an external adapter. Host-native routes retain their stated interception/observability limitation. Demo routes open no socket and are categorically forbidden from contributing evidence.

## 5. Routing Policy

### 5.1 Low

- Select one route only.
- Prefer a direct source-of-record adapter when the intent maps unambiguously to a canonical API or registry.
- Use host search/fetch for a known primary target.
- Use OpenAlex/Crossref/Semantic Scholar for explicit scholarly intent.
- Use Brave only when current independent discovery is necessary.
- Admit at most the bounded top results and fetch at most the decisive source set.

### 5.2 Medium

- Select one primary route: direct source-of-record, host, enabled independent index, enabled semantic route, or scholarly route by problem shape.
- Reserve one alternate-index challenge; do not spend it during initial discovery.
- Escalate sequentially when the first route misses source-of-record, freshness, region, or origin-diversity gates.
- Fetch selected URLs directly. Use Jina/Firecrawl only after a classified host-fetch failure.

### 5.3 High

- Require two index families only when the claim type actually needs independent discovery or challenge.
- Parallelize pre-authorized routes when latency matters and the expected unique-origin gain is material.
- Pair index families, not provider brands. Google grounding plus Serper is one family; model reports citing the same publisher remain one origin.
- Keep deep investigation separate from direct verification and source-origin promotion.

### 5.4 Fan-Out Triggers

A second route is eligible when at least one recorded condition holds:

- `primary_source_count < evidence_floor`
- `source_of_record_missing=true`
- `freshness_deadline_missed=true`
- `publisher_concentration_above_policy=true`
- `regional_or_language_gap=true`
- `live_hypothesis_discrimination_missing=true`
- `provider_health_degraded=true`
- `high_parallel_challenge_preapproved=true`

The second route still passes the lexicographic action policy. More results alone are not material state change.

## 6. Deterministic Fusion and Origin Tracing

Store three identities separately:

1. **Occurrence:** one provider result for one query and time.
2. **Document:** canonical URL, DOI/PMID/arXiv identifier, or fetched content fingerprint.
3. **Claim support:** an exact source span that entails one normalized claim.

Required occurrence fields include provider ID, index family, retrieval mode, query hash, request ID, raw URL, normalized comparison URL, redirect chain, provider rank/score, publication or page age, title, snippet, content hash, publisher root, identifier set, raw payload reference, and retention status.

Fusion procedure:

1. Preserve raw URLs exactly.
2. Normalize only comparison URLs; remove known tracking parameters but retain identity-changing parameters.
3. Resolve DOI, PMID, arXiv, and publisher identifiers before URL clustering.
4. Record redirects and treat `rel=canonical` as a hint, not truth.
5. Use deterministic content hashes and optional shingled fingerprints for near-duplicate clusters.
6. Use reciprocal-rank fusion only to order candidates, with at most one contribution per index family and a publisher-root cap.
7. Keep `retrieval_agreement` separate from `claim_corroboration`.
8. Promote corroboration only from exact entailing spans with independent source lineage.

Duplicate URLs, duplicate text, shared press releases, model agreement, and same-publisher repetition never become empirical corroboration.

## 7. Adoption Benchmark

Provider adoption uses the main harness coverage-matrix and sequential-stopping philosophy. It does not use a fixed query count as proof.

Coverage strata:

- volatile/current policy and product facts;
- source-of-record lookup;
- scientific and scholarly discovery;
- niche technical and long-tail discovery;
- non-English and regional queries relevant to actual use;
- adversarial stale, ambiguous, or SEO-heavy queries;
- host-fetch failure classes for extraction providers.

Metrics:

- primary-source recall at bounded ranks;
- source-of-record hit rate;
- novel canonical document and independent-publisher yield;
- freshness and stale-result rates;
- exact citation/span support;
- admitted tokens per supported claim;
- cost per novel primary source and supported claim;
- p50/p95 latency, timeout, rate-limit, retry, and partial-result rates;
- index-family overlap and publisher concentration;
- provenance completeness and replayability;
- privacy, retention, and lifecycle gate outcomes.

Before confirmatory runs, declare target strata, practical effect threshold, sequential method, maximum call budget, and privacy policy. Repeated queries estimate within-task variance and do not become independent samples.

Hard adoption gates:

- no lifecycle or privacy blocker;
- bounded call and token accounting;
- raw URL and query provenance survive successful calls;
- citations survive fusion and direct fetch;
- error/latency behavior fits the target tier;
- provider storage rights are compatible with artifact retention, or output remains explicitly ephemeral discovery metadata.

Direct source-of-record adapters do not need to beat a generic search engine on broad recall. They must instead pass schema/version fixtures, canonical-identifier accuracy, freshness, outage/error behavior, and exact-field provenance for their narrow declared intent.

Marginal-value gate:

The predeclared confidence boundary must show a practically meaningful improvement in at least one target metric without a hard-gate or stratum regression. Marketing claims, one impressive answer, and aggregate gains that hide a regional or scholarly regression do not enable a provider.

## 8. Retention and Privacy

Provider search responses are discovery metadata unless directly fetched source bytes establish evidence. Registry `storage_rights` controls whether the raw provider payload may be persisted.

`storage_rights` is structured, not prose: `payload_retention` is `forbidden`, `ephemeral`, `session`, or `persistent`; `html_allowed` is explicit; `allowed_operational_fields` lists any metadata that may survive an ephemeral response; and `verified_at` plus source URL record the policy basis. `unknown` fails closed for raw payload persistence. Every stored provider/processor artifact carries provider ID and occurrence/attempt ID so typed adapter ingestion can check the immutable session snapshot. Managed adapter spool files are excluded from generic local/user ingestion; a malicious filesystem owner who manually copies bytes and lies about origin is outside the process-integrity threat model and is not claimed as prevented.

- Brave plans require explicit storage rights to retain API results beyond allowed use; otherwise keep discovery payload ephemeral and persist only permitted operational metadata plus separately fetched source artifacts. [Brave Search API](https://brave.com/search/api/)
- Exa public-plan ZDR and retention guarantees are not assumed; enterprise ZDR is documented as a custom arrangement. [Exa security](https://exa.ai/docs/reference/security)
- Firecrawl caching is disabled for sensitive use where supported; it remains a fetch fallback. [Firecrawl scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape)
- Local/private research context is minimized before any search query and never sent merely to improve recall.

## 9. Adoption Order and Keys

Do not request every key up front.

1. Implement registry, result occurrence schema, and no-network adapters/fixtures.
2. Add the highest-used direct source-of-record adapters from retained development tasks; most begin keyless or reuse existing host credentials.
3. Add Brave adapter; request `BRAVE_SEARCH_API_KEY` for its benchmark.
4. Add OpenAlex and Crossref; request an OpenAlex key when the adapter fixtures pass. Crossref polite access uses an identifying `mailto`, not a secret API key.
5. Add Europe PMC keyless biomedical routing.
6. Implement Exa and Mojeek adapters behind `enabled=false`; request trial/procurement access only for the paired benchmark.
7. Enable Jina or Firecrawl only after host-fetch failure fixtures show a material gap; then request the chosen key.
8. Keep all other providers disabled until a named target route and adoption budget exist.

No paid provider benchmark runs without a user-confirmed evaluation call budget.

## 10. Rejected Defaults

- concurrent Google-plus-Brave on every query;
- using generic search when an authoritative structured source-of-record route is known;
- treating Google grounding and a Google SERP wrapper as independent;
- counting fetch/extract services as search-index diversity;
- enabling every available provider because a free tier exists;
- using model agreement as source corroboration;
- storing provider payloads when plan terms do not grant storage rights;
- routing by registry order or hard-coded provider priority;
- fixed provider benchmark size without variance or sequential evidence.

## 11. Revisit Conditions

Re-evaluate the portfolio when a provider changes index provenance, pricing unit, storage rights, privacy, lifecycle, or result schema; when retained route metrics show degradation; or when a new query class repeatedly fails current coverage gates. Registry updates require docs verification, fixture refresh, and targeted benchmark evidence before enablement.

## 12. Foundation Implementation Checkpoint

The v2 foundation now has a versioned registry, immutable per-session capability snapshots, secret-free preflight, exact route multiplicity, structured storage rights, and monotone overlay validation. Every external network provider remains `enabled=false`. Host-native, local, Organizer, and deterministic no-network test routes are the only enabled records; deterministic demo output is prohibited from canonical evidence.

This checkpoint does not implement the worker request boundary, common retrieval-occurrence adapters, deterministic fusion, or adoption benchmark runner. Therefore:

- existing credentials and legacy worker success do not establish execution readiness;
- no external route may acquire a v2 permit or persist provider payloads through the generic artifact CLI;
- no Brave, OpenAlex, Exa, Mojeek, Jina, Firecrawl, or other new key is requested yet;
- the next provider work starts with bound adapter fixtures and a named call budget, then runs the declared query-class benchmark before any enablement.
