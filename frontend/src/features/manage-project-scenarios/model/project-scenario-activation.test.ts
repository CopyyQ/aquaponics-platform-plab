import { describe, expect, it } from "vitest"

import type { ProjectScenarioSummary } from "@/api/contracts"
import { applyProjectScenarioActivation } from "@/features/manage-project-scenarios/model/project-scenario-activation"

const scenario = (
  id: string,
  name: string,
  isActive: boolean
): ProjectScenarioSummary => ({
  id,
  name,
  description: null,
  is_active: isActive,
  sensor_count: 12,
  actuator_count: 8,
  source_scenario_catalog_id: null,
  cloned_from_scenario_id: null,
  created_at: "2026-09-23T00:00:00Z",
  updated_at: "2026-09-23T00:00:00Z",
})

describe("applyProjectScenarioActivation", () => {
  it("marks only the activated scenario as active immediately", () => {
    const previous = scenario("old", "Kịch bản vận hành Aquaponics", true)
    const target = scenario("new", "Kịch bản nuôi cá thu", false)
    const activated = {
      ...target,
      is_active: true,
      updated_at: "2026-09-23T03:03:36Z",
    }

    const result = applyProjectScenarioActivation([previous, target], activated)

    expect(result).toEqual([
      { ...previous, is_active: false },
      activated,
    ])
  })

  it("keeps the cache undefined until the list query exists", () => {
    const activated = scenario("new", "Kịch bản nuôi cá thu", true)

    expect(applyProjectScenarioActivation(undefined, activated)).toBeUndefined()
  })
})
