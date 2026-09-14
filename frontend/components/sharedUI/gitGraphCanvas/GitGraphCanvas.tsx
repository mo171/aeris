"use client";

import React, { useMemo, useState, useRef, useEffect, useLayoutEffect } from "react";
import { cn } from "@/lib/utils";

export interface GitGraphNode {
  id: string;
  parents: string[];
  renderRow: (node: GitGraphNode, isExpanded: boolean, toggleExpand: () => void) => React.ReactNode;
  renderDetails?: (node: GitGraphNode) => React.ReactNode;
  color?: string; // Tailwind color class or hex for the node dot
}

interface GitGraphCanvasProps {
  nodes: GitGraphNode[];
  className?: string;
  rowHeight?: number; // Base height of a collapsed row
}

// Colors for different branches
const BRANCH_COLORS = [
  "#51A0E9", // Blue
  "#F27777", // Red
  "#79C267", // Green
  "#F09A50", // Orange
  "#A485E8", // Purple
  "#E2C044", // Yellow
];

export function GitGraphCanvas({ nodes, className, rowHeight = 48 }: GitGraphCanvasProps) {
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const [rowTops, setRowTops] = useState<number[]>([]);
  const [containerHeight, setContainerHeight] = useState(0);

  const toggleExpand = (id: string) => {
    setExpandedNodes((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const layout = useMemo(() => {
    const columns = new Map<string, number>();
    const rows = new Map<string, number>();
    const active = new Array<string | null>();

    nodes.forEach((n, i) => rows.set(n.id, i));

    let maxCol = 0;

    nodes.forEach((node, rowIndex) => {
      let col = active.indexOf(node.id);
      if (col === -1) {
        col = active.findIndex((c) => c === null);
        if (col === -1) {
          col = active.length;
          active.push(node.id);
        } else {
          active[col] = node.id;
        }
      }
      columns.set(node.id, col);
      if (col > maxCol) maxCol = col;

      if (node.parents.length > 0) {
        // The first parent continues on the same branch line
        active[col] = node.parents[0];
        
        // Additional parents branch off
        for (let i = 1; i < node.parents.length; i++) {
          const p = node.parents[i];
          if (!active.includes(p)) {
            const emptyCol = active.findIndex((c) => c === null);
            if (emptyCol === -1) {
              active.push(p);
            } else {
              active[emptyCol] = p;
            }
          }
        }
      } else {
        active[col] = null;
      }
    });

    // Compute edges
    const edges: { sourceId: string; targetId: string; sourceCol: number; targetCol: number; sourceRow: number; targetRow: number }[] = [];
    nodes.forEach((node) => {
      const sourceCol = columns.get(node.id)!;
      const sourceRow = rows.get(node.id)!;
      node.parents.forEach((parentId) => {
        const targetCol = columns.get(parentId);
        const targetRow = rows.get(parentId);
        if (targetCol !== undefined && targetRow !== undefined) {
          edges.push({
            sourceId: node.id,
            targetId: parentId,
            sourceCol,
            targetCol,
            sourceRow,
            targetRow,
          });
        }
      });
    });

    return { columns, rows, edges, maxCol };
  }, [nodes]);

  // Recompute node positions when expansion changes
  useLayoutEffect(() => {
    if (!containerRef.current) return;
    const rowElements = Array.from(containerRef.current.querySelectorAll('[data-row-index]'));
    const tops = rowElements.map((el) => (el as HTMLElement).offsetTop);
    setRowTops(tops);
    setContainerHeight(containerRef.current.scrollHeight);
  }, [nodes, expandedNodes, layout]);

  const SVG_WIDTH_PER_COL = 16;
  const SVG_PADDING = 24; // left padding
  const graphWidth = SVG_PADDING + (layout.maxCol + 1) * SVG_WIDTH_PER_COL + 16; // extra right padding

  return (
    <div className={cn("flex flex-col text-sm relative isolate w-full", className)} ref={containerRef}>
      {nodes.length === 0 ? (
        <div className="text-muted-foreground p-4 text-center text-xs">No history available.</div>
      ) : (
        <>
          {/* Overlay SVG for drawing paths */}
          <div className="absolute top-0 left-0 bottom-0 pointer-events-none z-10" style={{ width: graphWidth, height: containerHeight || '100%' }}>
            <svg className="w-full h-full overflow-visible">
              {rowTops.length === nodes.length && layout.edges.map((edge, eIdx) => {
                const sourceY = rowTops[edge.sourceRow] + rowHeight / 2;
                const targetY = rowTops[edge.targetRow] + rowHeight / 2;
                const sourceX = SVG_PADDING + edge.sourceCol * SVG_WIDTH_PER_COL;
                const targetX = SVG_PADDING + edge.targetCol * SVG_WIDTH_PER_COL;
                const edgeColor = BRANCH_COLORS[edge.targetCol % BRANCH_COLORS.length];

                if (edge.sourceCol === edge.targetCol) {
                  // Straight vertical line
                  return (
                    <line
                      key={`edge-${eIdx}`}
                      x1={sourceX}
                      y1={sourceY}
                      x2={targetX}
                      y2={targetY}
                      stroke={edgeColor}
                      strokeWidth={2}
                      fill="none"
                    />
                  );
                } else {
                  // Bezier curve to merge/branch
                  // Draw from source down then curve to target
                  const midY = sourceY + 16; // curve starts shortly after source
                  const path = `M ${sourceX} ${sourceY} C ${sourceX} ${midY}, ${targetX} ${midY}, ${targetX} ${targetY}`;
                  return (
                    <path
                      key={`edge-${eIdx}`}
                      d={path}
                      stroke={edgeColor}
                      strokeWidth={2}
                      fill="none"
                    />
                  );
                }
              })}
            </svg>
          </div>

          {/* Node Rows */}
          <div className="relative z-20 flex flex-col w-full">
            {nodes.map((node, index) => {
              const isExpanded = !!expandedNodes[node.id];
              const col = layout.columns.get(node.id) ?? 0;
              const cx = SVG_PADDING + col * SVG_WIDTH_PER_COL;
              const cy = rowHeight / 2;
              const nodeColor = node.color || BRANCH_COLORS[col % BRANCH_COLORS.length];

              return (
                <div
                  key={node.id}
                  data-row-index={index}
                  className="relative flex flex-col group min-h-[48px] border-b border-zinc-800/60 hover:bg-zinc-900/40 transition-colors w-full"
                >
                  {/* Content Layer */}
                  <div className="relative z-20 flex w-full" style={{ minHeight: rowHeight }}>
                    {/* Space for the graph */}
                    <div style={{ width: graphWidth, minWidth: graphWidth }} className="shrink-0 flex relative">
                      {/* Node Dot */}
                      <div 
                        className="absolute rounded-full border-[3px] border-[#09090b] z-20 shadow-sm transition-transform duration-200 group-hover:scale-110 cursor-pointer"
                        style={{ 
                          left: cx - 6, 
                          top: cy - 6, 
                          width: 12, 
                          height: 12, 
                          backgroundColor: nodeColor 
                        }}
                        onClick={() => toggleExpand(node.id)}
                      />
                    </div>
                    
                    {/* Row Content */}
                    <div className="flex-1 min-w-0 py-2 pr-4 flex flex-col justify-center cursor-pointer" onClick={() => toggleExpand(node.id)}>
                      {node.renderRow(node, isExpanded, () => toggleExpand(node.id))}
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && node.renderDetails && (
                    <div className="relative z-20 flex w-full pb-4 pt-1">
                      <div style={{ width: graphWidth, minWidth: graphWidth }} className="shrink-0" />
                      <div className="flex-1 min-w-0 pr-4">
                        <div className="bg-zinc-900/60 rounded-md border border-zinc-800/60 p-3 shadow-inner">
                          {node.renderDetails(node)}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
