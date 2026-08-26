// app/loading.tsx — the route transition placeholder.
//
// what  : A minimal branded holding screen shown while a route segment loads.
// where : Applies to every route in the application.
// how   : Deliberately quiet and short-lived. The Mission Command surface renders its own structure
//         immediately and each panel handles its own loading state, so this only ever appears during a
//         route transition — a detailed skeleton here would flash and then be replaced by a different
//         layout, which reads worse than a calm hold.

import { BrandLogo } from "@/components/sharedUI/dumbComponent/BrandLogo";

export default function RouteLoading() {
  return (
    <div className="flex h-dvh w-full flex-col items-center justify-center gap-4 bg-background">
      <BrandLogo />
      <p className="font-mono text-[10px] tracking-[0.22em] text-muted-foreground uppercase">
        Establishing uplink
      </p>
    </div>
  );
}
