---
workflow: explore_city
priority: medium
tags: [ranking, scoring, policy]
---

Default ranking heuristics for the `explore_city` flow:

  * **Anchor distance** is the primary spatial signal. If the user provided a
    home/work anchor it wins; otherwise the geocoded query result becomes the
    anchor. Penalty grows linearly at ~0.5 score-per-km — gentle enough that a
    great venue 3 km away still beats a mediocre one next door.
  * **Rating** contributes 2x the raw star value. Unrated venues default to
    zero rather than the category mean to avoid promoting unknown places.
  * **Preference match** (food_preferences, generic preferences) adds a flat
    +5 per matching type. This deliberately outweighs distance for the average
    query — users care more about *what fits them* than *what is closest*.
  * **Behavioural priors** from saved/clicked/ignored history adjust the score
    additively. Saved boosts are amplified by the `save_boost` multiplier; the
    runtime always passes 0 for first-time users.
  * **Budget gating** is soft: out-of-band price levels lose 2 points but are
    not filtered out. The downstream UI can show them dimmed.

Tie-breaking is stable on the original provider order, which preserves
provider-side ranking signal (Google's "prominence" sort, etc.) when our
scores are inconclusive.
