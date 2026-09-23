import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("thứ tự cơ cấu chấp hành trên trang thiết bị", () => {
  it("giữ thứ tự ổn định khi trạng thái runtime thay đổi", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/pages/device-detail-activation.tsx"),
      "utf8",
    );

    expect(source).toContain("const orderedActuators = [...value.actuators].sort");
    expect(source).toContain("left.actuator_model_id ?? Number.MAX_SAFE_INTEGER");
    expect(source).toContain("right.actuator_model_id ?? Number.MAX_SAFE_INTEGER");
    expect(source).toContain("orderedActuators.map((actuator)");
  });
});
