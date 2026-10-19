# Navis — Defect Report

**Date:** 2026-10-18 · **Scope:** `apps/api` (FastAPI runtime), `apps/web` (Next 16 / React 19), Docker/k8s config.

## How this was tested

| Activity | Result |
|---|---|
| Backend test suite (`pytest apps/api/tests`) | **89 passed**. Collection failed first because `httpx` is not in `requirements.txt`. |
| Frontend `tsc --noEmit`, `eslint src` | Clean |
| Live API battery (validation, 413 payloads, CORS, geocode, voice, 11 free-text queries, all 8 workflows, wire-contract leak check) | See findings |
| Load: 300× `/health` and 15 concurrent `/v2/query` from one IP | 249/300 and 15/15 got **429** |
| Browser walkthrough (onboarding, query, all pages via client-side navigation, dark/light, 375px mobile) | See findings |
| Static review of every backend and frontend module | See findings |

**Legend:** **[R]** reproduced at runtime · **[S]** confirmed by reading the code · ✅ fixed in this pass

---

## Critical — core features broken

1. **[R] Every AI summary is "I encountered an error trying to process the information."**
   - Cause: `services/providers/ai.py` hardcodes Groq model `llama-3.3-70b-versatile`. Groq returns 404 `model_not_found` for this key. The available models are `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, and others.
   - The HuggingFace fallback calls `api-inference.huggingface.co`, which doesn't resolve (DNS failure), and the HF key is reported invalid.
   - After 3 failures the AI circuit breaker opens and every request fails fast.
   - `HumanizationService.format_response` (`services/humanization.py`) returns this error text as the user-facing summary. `_deterministic_fallback` exists but is never used on this path.
2. **[R] The provider validator reports Groq "healthy" while it can't serve completions.** `_validate_groq` only pings `/models`, so the health panel can't be trusted.
3. **[S] Composed (multi-workflow) `/v2/query` results are always empty.** `runtime/passes/ingest.py` namespaces dependency ids (`explore_city__places_search`) but not FusionNode's plain-string `inputs`, so `fusion.py` skips every dependency. The e2e test only checks that sections exist.
4. **[R] Fusion collapses most results into one.** `services/fusion.py` builds identity from `name`/`title`/`id`. Geoapify GeoJSON features have none of these at the top level, so all of them collide on the key `"None"`.
   - Observed: "best cafes in chennai" → 1 result; "coworking spaces in Cambridge MA" → 1 result; the UI shows 1 card for "coffee shops near Boston Common".
5. **[S] API keys ship inside the Docker image.** `Dockerfile` runs `COPY apps/ ./apps/` with no `.dockerignore`, so `apps/api/.env` (8 provider keys), `apps/web/node_modules` and `api_legacy` all go into the image.

## High

6. **[R] Intent routing sends most queries to the wrong workflow.** Each of these fell through to `explore_city` with "no rule matched; default fallback":
   - "how long is the commute from Back Bay to Kendall Square" (should be `commute_analysis`)
   - "which neighborhood in Boston is good for families" (should be `neighborhood_match`)
   - "I'm moving to Boston next month, what should I do" (should be `relocation_plan`)
   - "coffee shops near Boston Common"
   - [S] Several `connect_mode` keywords ("meet people", "community", "startup") are gated out and can never fire (`runtime/intent/analyzer.py`).
7. **[R] Geocoding picks the wrong place.** The geo step uses the whole sentence. "which neighborhood in Boston…" anchored on **Boston Island, Southport, Maine** and returned restaurants in Boothbay.
   - "I'm moving to Boston next month…" failed to geocode, which then crashed places/events with `fetch() missing 2 required positional arguments: 'lat' and 'lon'`.
8. **[R] Rate limiting is too strict and shared by everything.** 60 req/min per IP across all endpoints (`core/security.py`). One home-page tab polls about 8 req/min. Several tabs, or any small load, trip it and the UI shows "Backend offline".
   - Behind a proxy or k8s ingress, all users share one bucket.
   - `_rate_store` never evicts entries.
9. **[S] Voice upload is effectively broken.**
   - The global `PayloadSizeMiddleware` caps every request at 64 KB, so any real recording over about 5 seconds gets 413.
   - [R] Even small uploads only get `transport_placeholder`: "Transcription is not yet implemented."
10. **[S] Internal events leak to clients, breaking the "invisible orchestration" rule.**
    - `/interact` streams `status`, `context_updated`, `agent_failed` (with exception text) and `agent_success`.
    - `/v2/workflow/{name}` emits `workflow_failed` with `details: str(exc)`. The frontend parser rejects that event, so users see "connection ended before a final result".
    - `test_ndjson_parsing.py` asserts the leaking behaviour.
11. **[S] The behaviour/interaction DB is never initialised.** `database.init_db()` is never called, so every queued write fails with "no such table". `/interaction/*` still returns `"success"`.
12. **[S] Provider failures are cached for 12–24 hours.** `ttl_cache` caches empty `[]` soft-failures, so one Geoapify timeout leaves that city empty for a day.
13. **[S] One user's data can bleed into another's.** Cached provider dicts are mutated in place by ranking (`rationale`, `score_breakdown`) and fusion (`_provenance`). Concurrent users can receive each other's personalised rationale.
14. **[S] The Docker setup doesn't work as written.**
    - The runtime image has no `curl`, so the `HEALTHCHECK` and the compose healthcheck always fail.
    - `knowledge/` isn't copied into the image, so `relocation_plan` and `essentials_checklist` return nothing in containers.
15. **[R] Frontend (dev): workflow pages hang after client-side navigation.** "Building your plan…" and "Loading your essentials…" spin forever. Cause: Strict Mode aborts the first run and the pages' run-once refs block the retry. ✅ **Fixed** in `hooks/useNavisWorkflow.ts`, which now resumes the interrupted run. Verified on `/plan`, `/essentials`, `/`, `/match`, `/explore` and `/commute`.
16. **[R] Frontend: the whole app rendered in Times New Roman.** `globals.css` had `--font-sans: var(--font-sans)`, a self-reference that is invalid, so Geist never applied. ✅ **Fixed.**
17. **[S] Frontend: the mic can stay on.** If `VoiceMicButton` unmounts while the browser permission prompt is open, recording starts anyway and isn't released (`useVoiceCapture.ts`).
18. **[S] Frontend: location autocomplete doesn't work from the keyboard.** Tabbing to an option blurs the input and closes the list; there's no arrow-key or Enter handling and no combobox ARIA. City, home and office can't be set without a mouse.

## Medium

19. **[R] `/metrics` returns "prometheus_client not installed".** `prometheus_client` and `psutil` are missing from requirements, even though k8s scrape annotations, Prometheus and Grafana are configured. Most metrics are never updated.
20. **[R] `httpx` is missing from `requirements.txt`.** Two test modules fail to collect without it.
21. **[R] Provider health panel labelled every provider "fallback", including healthy ones.** The badge meant "fallback available". ✅ Relabelled to a subtle "+ backup".
22. **[R] Raw Geoapify data is shown to users.** Cards show tags like `building.catering` and `catering.cafe.coffee`; coordinates come back as strings for some providers and floats for others.
23. **[R] The map ignores the user's city.** It opens centred on India for a Boston profile, and the suggestion chips are hardcoded to Chennai/Mumbai/T Nagar.
24. **[R] `/onboard` accepts `{}` and returns success.** `/interaction/*` takes any `user_id` with no auth, so anyone can poison any user's behaviour profile.
25. **[S] The stream concurrency guard doesn't work.** `StreamAbuseMiddleware` decrements before the streaming body is sent, and it only covers `/interact`.
26. **[S] The payload limit can be bypassed.** Chunked requests with no Content-Length skip it; a non-numeric Content-Length causes a 500.
27. **[S] Provider calls leak tasks on cancel.** In-flight node tasks aren't cancelled when the runner hard-cancels the scheduler on client disconnect, and `EventBus.stream` leaks a pending `Queue.get` task.
28. **[S] Geo provider URLs aren't encoded.** A `&` or `#` in the query injects parameters or truncates `apiKey`.
29. **[S] Every provider opens a new `aiohttp.ClientSession` per call**, ignoring the shared pool and `GLOBAL_TIMEOUT`.
30. **[S] One bad YAML file silently drops all later workflows.** `registry.load_dir` only catches `CompilerError`.
31. **[S] The fallback workflow always mixes in dining and events.** `explore_city.yaml` runs `events_search` and fixes the category to dining, so "universities in Boston" returns restaurants and concerts.
32. **[S] `DEBUG` defaults to `True`.**
33. **[S] Deployment config problems.** The k8s Secret manifest has empty values (applying it wipes real keys), and the Grafana admin password is hardcoded in `docker-compose.yml`.
34. **[S] `/providers/diagnostics` discloses config without auth.** It returns the absolute `.env` path plus each key's length and first character.
35. **[S] Neighborhood routing fans out with no concurrency limit** (24 candidates × modes), which trips Geoapify 429s.
36. **[S] Shutdown can hang.** `behavior_queue.stop()` awaits `join()` with no timeout.
37. **[S] Frontend: `/explore`, `/match` and `/commute` had no link anywhere in the UI.** ✅ Added to the new top nav and mobile tab bar.
38. **[S] Frontend: saved neighborhoods never appear on `/saved`.** They're stored as kind `location`, and the page's total excludes locations, so it shows "Nothing saved yet".
39. **[S] Frontend: the onboarding dialog isn't accessible.** No focus trap, no Escape to close, background not inert; labels aren't linked to inputs (`htmlFor`); chips have no `aria-pressed`.
40. **[S] Frontend: dark mode didn't persist and ignored the OS preference.** ✅ Fixed: persisted to localStorage, applied before paint, `color-scheme` set.
41. **[S] Frontend: Mapbox GL 3.x runs with the fake token `"navis-runtime"`.** [R] The console shows CORS-blocked telemetry posts to `events.mapbox.com`. Use `maplibre-gl` for MapTiler tiles.
42. **[S] Frontend: autocomplete reopens with stale results** after you pick an item while a request is still in flight.
43. **[S] Frontend: a trailing slash in `NEXT_PUBLIC_API_URL` breaks every call** (`//v2/query`), and a missing URL silently falls back to localhost.
44. **[S] Frontend: checklist and plan answers on the home page render "Nothing to show here yet."** Those workflows return `chunks`, not `results`.
45. **[S] Frontend: the office location can't be cleared from the profile.**

## Low

46. **[S] Unreachable branch:** `profiling.py`'s `elif lag > 0.5` can never fire.
47. **[S] Untracked profiling tasks:** they're never cancelled, and `revalidation_task` is cancelled but not awaited.
48. **[S] `optional:` in YAML does nothing.** `retries:` on provider nodes never triggers because `BaseProvider.execute` never raises.
49. **[S] Ranking personalisation is a no-op.** Field names don't match the provider data (`lng`/`lon`, `types`/`categories`).
50. **[S] False event signals:** "event" matches "prevent" and "party" matches "third-party".
51. **[S] Wrong timestamp:** `retrieved_at` uses the monotonic loop clock, not epoch time.
52. **[S] CWD-relative paths:** `knowledge`, `apps/api/workflows` and `./olaa.db` only resolve from the repo root.
53. **[S] Retired endpoint:** the Eventbrite fallback calls `/v3/events/search/`.
54. **[S] Unformatted logs:** printf-style structlog calls never get their arguments filled in.
55. **[S] Weak or flaky tests:** `test_view_filter.py` is tautological, and the streaming tests hit real networks and share the global rate limiter.
56. **[S] Frontend: duplicate React keys** for same-named places. ✅ Fixed in `ResultStream`. Saving one same-named place still marks both as saved (`PlaceCard`).
57. **[S] Frontend: the query box had no length cap** (the backend allows 2000 characters). ✅ `maxLength` added.
58. **[S] Frontend: the health badge flashes "offline"** when a check is superseded; the provider timestamp goes stale.
59. **[S] Frontend: `useNavisWorkflow` appends every heartbeat** to an `events` array that nothing reads.
60. **[S] Frontend: low contrast** on the SaveButton icon and 10px captions; the map `aria-label` is on a div with no role.
61. **[S] Shared types package is empty:** `packages/shared-types` has no sources, so wire types are hand-copied.
62. **[R] Placeholder routes:** `/connect`, `/move`, `/services`, `/taste`, `/transit` and `/voice` are aliases of the home page, while the README advertises 10 distinct pillars.

---

## UI modernisation (done in this pass)

- **Design system** (`globals.css`):
  - Remapped the `zinc`/`indigo` scales, so every existing page is re-skinned without touching each component: cooler neutrals, a violet-indigo accent.
  - Fixed the font, added light/dark tokens, ambient gradient backdrop, glass, soft/glow shadows, a shimmer skeleton animation and reduced-motion support.
- **Shell** (`AppLayout.tsx`):
  - Glass sticky header with a gradient logo and pill navigation (Ask, Explore, Neighborhoods, Commute, Plan, Essentials) with active state and `aria-current`.
  - Icon utilities; a floating mobile tab bar under 768px.
- **Theme:** persisted dark mode with a no-flash pre-paint script, OS preference as the default, and `themeColor`.
- **Home:** large gradient headline, a prominent search "command bar" with a glow shadow, an "Ask ↑" button, refreshed suggestion chips, a "Navis" answer card, skeleton loaders, and the dashboard moved below the workspace.
- **Components:** rounder buttons with a primary glow, translucent cards with hover lift on results, a modern onboarding dialog (zoom-in, gradient progress), and a cleaner provider list.
- **Verified:** desktop light/dark and 375px mobile (no horizontal scroll); all routes load after client-side navigation; `tsc` and `eslint` are clean.

## Suggested fix order

1. Make the Groq model configurable and switch to an available one, use the deterministic fallback instead of the error string, and make the validator test a real completion. (#1, #2)
2. Fix the fusion identity key and the composed-input namespacing. (#3, #4)
3. Add a `.dockerignore`, curl in the runtime stage, and copy `knowledge/`. (#5, #14)
4. Intent and geocoding: extract the place entity before geocoding; add commute, neighborhood and relocation rules. (#6, #7)
5. Rate limiting: exempt `/health` and `/providers/*`, raise the limit, and key on the forwarded IP. Raise the payload limit for `/v2/voice`. (#8, #9)
6. Scrub `/interact` and `/v2/workflow` to the 4 allowed events. (#10)
