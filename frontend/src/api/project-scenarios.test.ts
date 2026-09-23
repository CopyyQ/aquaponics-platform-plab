import { describe, expect, it } from "vitest"

import { endpoints, queryKeys } from "./resources"

describe("project scenario API contract", () => {
  it("keeps scenario lifecycle nested under one Device", () => {
    expect(endpoints.projectScenarios("s", "d")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios",
    )
    expect(endpoints.projectScenario("s", "d", "x")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x",
    )
    expect(endpoints.projectScenarioActivate("s", "d", "x")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x/activate",
    )
    expect(endpoints.projectScenarioClone("s", "d", "x")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x/clone",
    )
    expect(endpoints.projectScenarioItem("s", "d", "x", "i")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x/items/i",
    )
    expect(endpoints.projectScenarioBranches("s", "d", "x", "i")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x/items/i/branches",
    )
    expect(endpoints.projectScenarioBranch("s", "d", "x", "i", "b")).toBe(
      "/aquaponics-systems/s/devices/d/scenarios/x/items/i/branches/b",
    )
  })

  it("uses scenario-specific query keys instead of runtime-scenario aggregate keys", () => {
    expect(queryKeys.projectScenarios("s", "d")).toEqual([
      "aquaponics-system",
      "s",
      "device",
      "d",
      "scenarios",
    ])
    expect(queryKeys.projectScenario("s", "d", "x")).toEqual([
      "aquaponics-system",
      "s",
      "device",
      "d",
      "scenario",
      "x",
    ])
  })
})
