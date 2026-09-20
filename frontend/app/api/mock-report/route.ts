import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const format = searchParams.get("format");
  const id = searchParams.get("id") ?? "mumbai_investigation";

  if (format === "geojson") {
    return NextResponse.json({ type: "FeatureCollection", features: [] });
  }

  return NextResponse.json({ investigationId: id, status: "ok" });
}
