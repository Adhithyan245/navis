# OLAA / Native

A full-stack, global city platform designed to act as a unified interface for newcomers to settle, explore, connect, and thrive in any city worldwide.

## Product Architecture

The platform has evolved from a narrow MVP into a scalable 10-pillar architecture:
1. **Home (Dashboard)**: Central, context-aware entry point.
2. **Settle**: Move-in tasks, utilities, and logistics.
3. **Explore**: Place discovery, food, and neighborhood secrets (formerly Taste).
4. **Connect**: Events, meetups, and user communities.
5. **Move**: Transit, mobility, and commute-aware routing.
6. **Services**: Healthcare helper, pharmacies, urgent care, and emergency contacts.
7. **Work**: Coworking, study spaces, and professional networking.
8. **Saved**: Persistent vault for saved places, tasks, and history.
9. **Ask Native**: Universal voice/text interface routing across all domains.
10. **Profile**: Editable global context, preferences, and dislikes.

## Tech Stack

- `apps/web`: Next.js frontend (App Router, Tailwind CSS, shadcn/ui)
- `apps/api`: FastAPI backend (Async streaming orchestration)
- `packages/shared-types`: Shared TypeScript definitions
- `packages/shared-config`: Shared monorepo configuration

## Strict Anti-Hallucination Compliance

This system enforces a **strict zero-hallucination policy**. 
- Agents do not invent business locations, transit times, events, or healthcare providers.
- All 10 product pillars rely on real API data or explicit fallback schemas (e.g., `[]`).
- We expose data provenance directly in the UI via the `SourceBadge` (showing `Live`, `Mixed`, or `Fallback`).

## Setup

1. Copy `.env.example` to `.env` in the root and provide actual API keys to enable live data.
   - `GOOGLE_PLACES_API_KEY`: Required for Explore, Work, and Taste domains.
   - `NEXT_PUBLIC_MAPBOX_TOKEN`: Required for Mapbox rendering.
   - `MBTA_API_KEY`: Optional but recommended for Move/Transit features.
2. For Backend:
   ```bash
   cd apps/api
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. For Frontend:
   ```bash
   cd apps/web
   npm install
   npm run dev
   ```
