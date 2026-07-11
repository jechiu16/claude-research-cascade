# Exa vs Brave paired index benchmark

Date: 2026-07-11

Decision: enable Exa for anti-lock-in and verification. Keep Brave as the
default general scout.

Five identical development-research queries were sent once to each provider,
for ten physical requests total. Raw responses and result URLs were held only
in memory and were not committed. The benchmark stayed within the confirmed
10-request / US$0.10 envelope.

| Metric | Brave | Exa |
|---|---:|---:|
| Valid citations | 86 | 48 |
| Unique versus the paired provider | 66 | 28 |
| Shared citations | 20 | 20 |
| Provider-reported cost | unavailable | US$0.035 |

Exa added 28 valid URLs absent from Brave across all five queries, so it clears
the narrow independent-index value gate. Brave returned broader result lists
and remains the primary general-search route. Neither listing can support a
claim until the decisive source is fetched directly.

This is an adoption check, not a universal search-quality ranking. The sample
is deliberately small and development-focused; routing should still follow
query class, source-of-record preference, and the confirmed contract.
