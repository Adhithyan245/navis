---
workflow: explore_city
priority: high
tags: [orchestration, defaults]
---

`explore_city` is the canonical discovery workflow: given a user query that
references a place ("best cafes in chennai", "things to do near elliot's
beach"), produce a ranked, context-aware set of places, events, and transit
notes.

Pipeline contract:

  1. `retrieve_context` reads the corpus for city/tag-relevant intel and seeds
     downstream nodes with explainable orchestration guidance.
  2. `geo_search` resolves the query to a coordinate anchor. If this fails the
     whole run degrades to a generic response — there is no point running
     place/transit lookups without a location anchor.
  3. `places_search`, `events_search`, and `transit_analysis` run in parallel
     against the anchor. Any single one may fail; ranking proceeds with whatever
     succeeded.
  4. `fuse_results` deduplicates by name/title/id across providers.
  5. `rank_results` applies the standard place ranking (distance + rating +
     preference match + behavioural priors).
  6. `humanization` produces a short, conversational summary suitable for
     leading the streamed response.
  7. `stream_results` emits the final payload.

Hard rules:

  * Internal node lifecycle events MUST NOT cross the wire. The user sees the
    humanized prose, the ranked list, and a transit aside — never the
    machinery.
  * Provider fallbacks ARE acceptable and silent. A degraded provider
    contributes whatever it can; failure is logged but never user-facing.
  * Partial results are encouraged: emit a `partial_result` as soon as the
    ranked list is ready, then a `final_result` once humanization completes.
