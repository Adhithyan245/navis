---
workflow: work_mode
priority: high
tags: [work, coworking, cafes, remote, defaults]
---

`work_mode` answers "where can I sit down and work?" — laptop-friendly cafes,
coworking spaces, and the kind of restaurant where a 2-hour stay over coffee
and a meal is socially acceptable.

Ranking biases vs. `explore_city`:

  * Daytime open-hours matter much more than rating. A 4.8-star place that
    closes at 4 PM is useless for a 3 PM "find me a spot" query.
  * Power outlets and wifi presence (when surfaced by the provider) are
    decisive signals. They beat distance.
  * Density preference: a cluster of 3 acceptable options is often more
    useful than 1 perfect option further away — supports the "I'll walk
    over and pick on arrival" workflow.

Provider strategy: parallel `cafe` and `dining` category searches against
the places provider — the dining query catches the upscale-casual category
that's missing from a pure cafe search but is the right answer for someone
asking "where can I work + grab lunch?"

Anti-patterns:
  * Don't surface bars, clubs, or pure tourist venues even when they're
    technically open during work hours.
  * Don't trust generic "highly rated" signal — work-friendliness is a
    different axis from food quality.
