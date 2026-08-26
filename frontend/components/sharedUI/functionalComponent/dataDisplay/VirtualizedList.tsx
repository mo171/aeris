// components/sharedUI/functionalComponent/dataDisplay/VirtualizedList.tsx — windowed list for unbounded data.
//
// what  : Renders only the rows currently in view, supports dynamic row heights, and fires a callback when
//         the operator approaches the end so the caller can load the next page.
// where : Used by the imagery catalogue, the mission list, and any future list that can exceed a screen.
// how   : The imagery catalogue is unbounded — tens of thousands of scenes is a normal working set — and
//         mounting a component per scene would exhaust memory and destroy scroll performance long before
//         that. Virtualisation keeps the DOM node count constant regardless of data size, which is what
//         makes the panel's cost independent of the backend's.
//
//         Row measurement uses measureElement so rows with wrapped titles settle to their real height
//         instead of jumping; estimateItemHeight only needs to be approximately right.

"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

interface VirtualizedListProps<TItem> {
  items: readonly TItem[];
  estimateItemHeight: number;
  getItemKey: (item: TItem, index: number) => string;
  renderItem: (item: TItem, index: number) => ReactNode;
  /** Called when the viewport comes within `endReachedOffsetPx` of the bottom. */
  onEndReached?: () => void;
  endReachedOffsetPx?: number;
  overscan?: number;
  /** Rendered below the last row — used for the "loading more" indicator. */
  footer?: ReactNode;
  className?: string;
}

export function VirtualizedList<TItem>({
  items,
  estimateItemHeight,
  getItemKey,
  renderItem,
  onEndReached,
  endReachedOffsetPx = 320,
  overscan = 6,
  footer,
  className,
}: VirtualizedListProps<TItem>) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const hasRequestedForLengthRef = useRef(-1);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => estimateItemHeight,
    overscan,
  });

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container || !onEndReached) {
      return;
    }

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;

    // Guarding on the item count stops a burst of scroll events from firing the same page request
    // repeatedly while the request is still in flight.
    if (distanceFromBottom < endReachedOffsetPx && hasRequestedForLengthRef.current !== items.length) {
      hasRequestedForLengthRef.current = items.length;
      onEndReached();
    }
  }, [endReachedOffsetPx, items.length, onEndReached]);

  // A short list may not fill the viewport, in which case no scroll event ever fires and pagination
  // would stall on the first page.
  useEffect(() => {
    handleScroll();
  }, [handleScroll]);

  const virtualRows = virtualizer.getVirtualItems();

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className={cn("relative min-h-0 flex-1 overflow-y-auto overscroll-contain", className)}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
        {virtualRows.map((virtualRow) => {
          const item = items[virtualRow.index];

          return (
            <div
              key={getItemKey(item, virtualRow.index)}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {renderItem(item, virtualRow.index)}
            </div>
          );
        })}
      </div>
      {footer}
    </div>
  );
}
