import { describe, expect, it } from "vitest"

import {
  isActuatorCommandPendingFor,
  runtimeRefetchInterval,
} from "@/features/manage-actuator/model/device-runtime-refresh"

describe("device runtime refresh", () => {
  it("keeps the device page polling while the tab is visible", () => {
    expect(runtimeRefetchInterval("visible")).toBe(2000)
    expect(runtimeRefetchInterval("hidden")).toBe(false)
  })

  it("marks only the actuator that owns the pending command", () => {
    const pending = {
      actuatorId: "actuator-a",
      desiredState: true,
    }

    expect(isActuatorCommandPendingFor(true, pending, "actuator-a")).toBe(true)
    expect(isActuatorCommandPendingFor(true, pending, "actuator-b")).toBe(false)
    expect(isActuatorCommandPendingFor(false, pending, "actuator-a")).toBe(false)
    expect(isActuatorCommandPendingFor(true, undefined, "actuator-a")).toBe(false)
  })
})
