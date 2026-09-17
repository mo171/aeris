"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Image from "next/image";

import type { z } from "zod";
import type { figureReadyEventSchema } from "@/features/investigation/schemas/analysis.schema";

type FigureEvent = z.infer<typeof figureReadyEventSchema>;

export default function FigurePage() {
  const searchParams = useSearchParams();
  const figureId = searchParams.get("figureId");
  const [figure, setFigure] = useState<FigureEvent | null>(null);

  useEffect(() => {
    if (figureId) {
      const stored = localStorage.getItem(`aeris-figure-${figureId}`);
      if (stored) {
        try {
          setFigure(JSON.parse(stored));
        } catch (e) {
          console.error("Failed to parse figure data", e);
        }
      }
    }
  }, [figureId]);

  if (!figure) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-zinc-950 text-zinc-400">
        <p>Loading figure...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-50 p-6">
      <header className="mb-6 flex flex-col gap-1 border-b border-zinc-800 pb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-medium text-zinc-100">{figure.title}</h1>
          <span className="rounded bg-zinc-800 px-2 py-1 text-xs font-medium text-zinc-400 uppercase tracking-wider">
            {figure.kind.replace("-", " ")}
          </span>
        </div>
        {figure.caption && (
          <p className="text-sm text-zinc-400 max-w-3xl">{figure.caption}</p>
        )}
      </header>

      <main className="flex-1 flex flex-col items-center justify-center relative rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
        {/* We use a regular img tag because the source might be an arbitrary external URL from the backend that next/image doesn't allow in next.config.js */}
        <img
          src={figure.imageUrl}
          alt={figure.title}
          className="object-contain w-full h-full max-h-[80vh]"
          style={{ width: figure.width, height: figure.height }}
        />
      </main>

      {figure.legend && (
        <footer className="mt-6 flex flex-col gap-2 rounded-md border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="text-sm font-medium text-zinc-300">{figure.legend.label}</h3>
          {figure.legend.entries ? (
            <div className="flex flex-wrap gap-4">
              {figure.legend.entries.map((entry, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <div
                    className="h-4 w-4 rounded-sm"
                    style={{ backgroundColor: entry.color }}
                  />
                  <span className="text-xs text-zinc-400">{entry.label}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-between w-full max-w-md h-4 rounded bg-gradient-to-r from-transparent to-white opacity-80" />
            // Placeholder for continuous ramp
          )}
        </footer>
      )}
    </div>
  );
}
