// components/sharedUI/functionalComponent/appShell/NavigationRail.tsx — global navigation across all surfaces.
//
// what  : A vertical icon rail listing the seven AERIS surfaces, expandable to show labels, with the
//         current route highlighted and unbuilt surfaces shown as unavailable.
// where : Rendered by AppShell, so every page inherits identical navigation.
// how   : Items come from lib/constants/navigation.ts rather than being written here, which is what lets
//         the same list drive both this rail and the command palette. Surfaces that do not exist yet
//         render dimmed and non-interactive instead of linking to a 404 — the operator can see the shape
//         of the platform without hitting a dead end.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeft } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NAVIGATION_ITEMS, type NavigationItem } from "@/lib/constants/navigation";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";

export function NavigationRail() {
  const pathname = usePathname();
  const isExpanded = useUiStore((state) => state.isNavigationRailExpanded);
  const toggleNavigationRail = useUiStore((state) => state.toggleNavigationRail);

  return (
    <nav
      aria-label="AERIS surfaces"
      data-expanded={isExpanded}
      className={cn(
        "z-30 flex shrink-0 flex-col border-r border-border bg-sidebar backdrop-blur-md transition-[width] duration-base ease-expo",
        isExpanded ? "w-52" : "w-14",
      )}
    >
      <ul className="flex flex-1 flex-col gap-1 p-2">
        {NAVIGATION_ITEMS.map((item) => (
          <li key={item.id}>
            <NavigationRailItem
              item={item}
              isActive={pathname === item.href}
              isExpanded={isExpanded}
            />
          </li>
        ))}
      </ul>

      <div className="p-2">
        <button
          type="button"
          onClick={toggleNavigationRail}
          aria-label={isExpanded ? "Collapse navigation" : "Expand navigation"}
          aria-expanded={isExpanded}
          className="flex h-9 w-full items-center gap-3 rounded-md px-2.5 text-muted-foreground transition-colors duration-fast hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <PanelLeft
            className={cn(
              "size-4 shrink-0 transition-transform duration-base ease-expo",
              isExpanded && "rotate-180",
            )}
            aria-hidden="true"
          />
          {isExpanded ? <span className="truncate text-xs">Collapse</span> : null}
        </button>
      </div>
    </nav>
  );
}

interface NavigationRailItemProps {
  item: NavigationItem;
  isActive: boolean;
  isExpanded: boolean;
}

function NavigationRailItem({ item, isActive, isExpanded }: NavigationRailItemProps) {
  const Icon = item.icon;

  const content = (
    <span
      className={cn(
        "group/nav relative flex h-9 items-center gap-3 rounded-md px-2.5 transition-colors duration-fast",
        isActive
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
        !item.isAvailable && "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-muted-foreground",
      )}
    >
      {/* Active marker: a short teal bar tucked against the rail edge. */}
      <span
        aria-hidden="true"
        className={cn(
          "absolute top-1/2 -left-2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-aeris-teal transition-opacity duration-base",
          isActive ? "opacity-100 shadow-glow-teal" : "opacity-0",
        )}
      />
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {isExpanded ? <span className="truncate text-xs">{item.label}</span> : null}
      {isExpanded && !item.isAvailable ? (
        <span className="ml-auto font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
          Soon
        </span>
      ) : null}
    </span>
  );

  if (!item.isAvailable) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <div aria-disabled="true">{content}</div>
        </TooltipTrigger>
        <TooltipContent side="right">
          <span className="flex flex-col gap-0.5">
            <span className="font-medium">{item.label}</span>
            <span className="opacity-70">Not built yet</span>
          </span>
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link href={item.href} aria-current={isActive ? "page" : undefined} className="block">
          {content}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right">
        <span className="flex flex-col gap-0.5">
          <span className="font-medium">{item.label}</span>
          <span className="opacity-70">{item.description}</span>
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
