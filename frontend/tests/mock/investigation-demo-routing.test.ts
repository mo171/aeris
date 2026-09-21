import { describe, expect, it } from "vitest";

import { createMockInvestigation } from "../../mock/data/investigation.data";

const MUMBAI_DEMO_SCENES = [
  "SCN_01M2ZGSPQA1XFMJD4AJ6MHQRXD",
  "SCN_01M289GQ9QMFQY7YGAFMFPSWDP",
] as const;

describe("mock investigation demo routing", () => {
  it("keeps the core Mumbai demo scenes on the Mumbai investigation", () => {
    const investigation = createMockInvestigation(MUMBAI_DEMO_SCENES, null, null);

    expect(investigation.areaOfInterestName).toBe("Mumbai Coastal Belt & Port Zone, India");
    expect(investigation.centroid).toEqual({ latitude: 18.975, longitude: 72.86 });
    expect(investigation.sceneSlots.map((slot) => slot.name)).toContain(
      "Mumbai Coastal Belt · Sentinel-2B (T0)",
    );
  });

  it("routes any non-Mumbai catalogue selection to the Gulf Coast Refineries demo", () => {
    const investigation = createMockInvestigation(["scn_000137"], null, null);

    expect(investigation.areaOfInterestName).toBe("Gulf Coast Refineries, United States");
    expect(investigation.centroid).toEqual({ latitude: 29.76, longitude: -95.37 });
    expect(investigation.areaOfInterest).toEqual({
      west: -95.62,
      south: 29.55,
      east: -95.07,
      north: 29.93,
    });
    expect(investigation.sceneSlots.every((slot) => slot.name.startsWith("Gulf Coast Refineries"))).toBe(
      true,
    );
  });
});
