// app/(reference)/models/page.tsx — the Model Observatory.
//
// what  : The specialist model registry: capability, version, live health, and the routing rule behind
//         each selection.
// where : Reached from the navigation rail, from the model fleet strip on Mission Command, and from any
//         model name in an execution trace.
// how   : In the (reference) group rather than (geospatial) — it answers questions about the system, not
//         about a place, so it must not pay for a WebGL context it never draws into.

import { ModelObservatoryScreen } from "@/features/modelObservatory/components/ModelObservatoryScreen";

export default function ModelObservatoryPage() {
  return <ModelObservatoryScreen />;
}
