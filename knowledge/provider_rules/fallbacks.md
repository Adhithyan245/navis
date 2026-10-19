---
priority: high
tags: [providers, fallback, resiliency]
---

Provider routing and fallback policy for the runtime:

  * **Geo**: primary is the configured geocoder; on failure or empty results
    the run should NOT proceed to place/event/transit lookups. Mark the
    geo node `optional: false` even though most others are `optional: true`.
  * **Places**: degrade silently to whatever the provider returns, including
    `source: fallback` responses. Ranking handles empty result sets gracefully.
  * **Events**: optional in every workflow. Many cities have no event provider
    coverage; an empty events list is the expected state, not a failure.
  * **Transit**: optional but high-value when present. If transit returns
    nothing, the humanization layer should not fabricate transit guidance —
    omit the transit clause entirely.

Provider fallbacks are a normal operating mode. They are logged via the
`PROVIDER_FALLBACK` internal event for observability but never surface to the
client. Users see ranked results; they don't see why some came from a backup
endpoint.
