import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("bật tắt cảm biến trên trang thiết bị", () => {
  it("cho phép bật hoặc tắt từng cảm biến độc lập", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/pages/device-detail-activation.tsx"),
      "utf8",
    )

    expect(source).toContain("updateSensor")
    expect(source).toContain("sensorLifecycle")
    expect(source).toContain("Bật cảm biến")
    expect(source).toContain("Tắt cảm biến")
    expect(source).toContain("sensorLifecycle.mutate")
    expect(source).toContain("variables?.sensorId === sensor.id")
  })
})
