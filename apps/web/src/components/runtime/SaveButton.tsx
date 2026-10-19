"use client";
/**
 * SaveButton — toggles a single item's saved state via SavedItemsContext.
 *
 * The caller supplies a fully-formed SavedItem (minus a meaningful savedAt);
 * this component stamps savedAt at save time. Read-only field access — no
 * backend, no sync; persistence is localStorage via the context.
 */
import { Bookmark, BookmarkCheck } from "lucide-react";

import { useSavedItemsContext } from "@/lib/saved/context";
import type { SavedItem } from "@/lib/saved/schema";
import { cn } from "@/lib/utils";

export function SaveButton({
  item,
  className,
}: {
  item: SavedItem;
  className?: string;
}) {
  const { isSaved, saveItem, removeItem } = useSavedItemsContext();
  const saved = isSaved(item.kind, item.id);

  const toggle = () => {
    if (saved) {
      removeItem(item.kind, item.id);
    } else {
      saveItem({ ...item, savedAt: Date.now() });
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={saved}
      aria-label={saved ? "Remove from saved" : "Save"}
      title={saved ? "Saved" : "Save"}
      className={cn(
        "inline-flex size-7 shrink-0 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-muted hover:text-foreground dark:hover:bg-muted/50 [&_svg]:size-4",
        saved && "text-indigo-500 dark:text-indigo-400",
        className
      )}
    >
      {saved ? <BookmarkCheck /> : <Bookmark />}
    </button>
  );
}
