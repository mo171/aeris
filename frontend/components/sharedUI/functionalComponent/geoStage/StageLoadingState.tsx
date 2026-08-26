// components/sharedUI/functionalComponent/geoStage/StageLoadingState.tsx — the stage's boot and unsupported states.
//
// what  : A centred technical placeholder with a faint grid and an orbital ring, plus a WebGL-unavailable
//         variant carrying a real explanation.
// where : Shown by GeoStage while the 3D bundle downloads, and permanently when WebGL is missing.
// how   : It occupies exactly the same box as the finished globe, so the panels around it never reflow
//         when the canvas takes over. It is also intentionally quiet: a loud spinner in the centre of the
//         command centre would be the first thing an operator sees every session.

import { Orbit, TriangleAlert } from "lucide-react";

export function StageLoadingState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="aeris-grid-backdrop absolute inset-0" aria-hidden="true" />
      <div className="relative flex flex-col items-center gap-3">
        <span className="relative flex size-16 items-center justify-center">
          <span className="absolute inset-0 animate-[spin_5s_linear_infinite] rounded-full border border-aeris-teal/25 border-t-aeris-teal/80" />
          <Orbit className="size-5 text-aeris-teal/70" aria-hidden="true" />
        </span>
        <p className="font-mono text-[10px] tracking-[0.2em] text-muted-foreground uppercase">
          Initialising orbital view
        </p>
      </div>
    </div>
  );
}

export function StageUnavailableState() {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="aeris-grid-backdrop absolute inset-0" aria-hidden="true" />
      <div className="relative flex max-w-xs flex-col items-center gap-2 text-center">
        <span className="flex size-9 items-center justify-center rounded-md border border-aeris-amber/35 bg-aeris-amber/10">
          <TriangleAlert className="size-4 text-aeris-amber" aria-hidden="true" />
        </span>
        <p className="text-xs font-medium text-foreground">3D view unavailable</p>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          This browser has no WebGL context, so the orbital view cannot render. Every other part of the
          command centre works normally — imagery intake, the catalogue and the assistant are unaffected.
        </p>
      </div>
    </div>
  );
}
