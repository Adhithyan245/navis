"use client";
/**
 * QueryWorkspace — the conversational page's stateful root.
 *
 * Owns useNavisQuery so the same partial/final state drives:
 *   * the text result stream (QueryConsole)
 *   * the live map (ResultMap, driven by useResultMarkers)
 *   * any future runtime-derived view (sidebar, transit overlay, etc.)
 *
 * Server-side rendering yields the bare layout; everything below this
 * boundary is client-rendered (state, streaming, browser APIs).
 */
import { QueryConsole } from "@/components/runtime/QueryConsole";
import { ResultMap } from "@/components/runtime/ResultMap";
import { useNavisQuery } from "@/hooks/useNavisQuery";
import { useResultMarkers } from "@/hooks/useResultMarkers";
import { useProfileContext } from "@/lib/profile/context";

export function QueryWorkspace() {
  const query = useNavisQuery();
  const { profile } = useProfileContext();
  const markers = useResultMarkers({
    partials: query.partials,
    final: query.final,
  });

  return (
    <div className="grid w-full grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
      <div className="min-w-0">
        <QueryConsole state={query} />
      </div>
      <aside className="flex flex-col gap-6">
        <ResultMap
          anchor={markers.anchor}
          items={markers.items}
          hasMarkers={markers.hasMarkers}
          home={profile?.cityLocation ?? null}
        />
      </aside>
    </div>
  );
}
