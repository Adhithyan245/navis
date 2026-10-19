---
workflow: connect_mode
priority: high
tags: [events, networking, social, meetup, defaults]
---

`connect_mode` answers "what's happening?" — concerts, meetups, networking
events, talks, and other time-bound social happenings near an anchor.

Pipeline emphasis: the events provider is `optional: false` because
without events data the entire workflow loses its reason for existing.
Fusion will combine event payloads with adjacent venue places so the
final response can answer follow-ups like "what's at that venue
tonight?" without a second round trip.

Ranking biases vs. `explore_city`:

  * Time proximity dominates — an excellent event next week beats an
    okay event tonight only marginally; an event that already started
    is filtered out entirely upstream when possible.
  * Category match against `user_context.event_categories` is the
    strongest preference signal.
  * Distance penalty is gentler than for places — users routinely
    travel further for an event than for a coffee.

Anti-patterns:
  * Don't surface recurring weekly events without distinguishing
    "tonight's instance" from "the series." Surface the instance.
  * Don't backfill from places when events came back empty — better
    to acknowledge no events found than to pivot silently.
