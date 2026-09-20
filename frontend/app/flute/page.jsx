import React from "react";
import { notFound } from "next/navigation";
import FluteStudio from "../../src/flute/Studio";
export default function FlutePage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <><meta name="flute-project" content="87e12401-03f1-45a7-8c04-860e26ccd5af" /><FluteStudio /></>;
}
