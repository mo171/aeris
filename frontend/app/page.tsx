// app/page.tsx — the Mission Command Center route.
//
// what  : Routes "/" to the Mission Command Center surface.
// where : The application entry point.
// how   : Deliberately one line of JSX. Pages are route entry points and nothing else — all composition,
//         state and data belong to the feature module, which is what lets the same surface be reused or
//         relocated without touching routing.

import { MissionCommandScreen } from "@/features/missionCommand/components/MissionCommandScreen";

export default function MissionCommandPage() {
  return <MissionCommandScreen />;
}
