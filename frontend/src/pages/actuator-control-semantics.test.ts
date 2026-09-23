import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("ngu nghia dieu khien actuator", () => {
  it("trang device coi desired/reported va canh bao dien la thong tin, khong phai interlock", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/pages/device-detail-activation.tsx"),
      "utf8",
    );

    expect(source).toContain("actuatorCommandAvailability");
    expect(source).toContain("Trạng thái báo về gần nhất");
    expect(source).toContain("runtime?.active_alert");
    expect(source).not.toContain("const awaitingAck");
    expect(source).not.toContain("actuator.reported_state === true");
    expect(source).not.toContain("actuator.reported_state === false");
  });

  it("trang chi tiet cung cho ACK thiet bi va khong khoa vi canh bao dien", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/pages/actuator-detail-canonical.tsx"),
      "utf8",
    );

    expect(source).toContain("waitForActuatorCommandFeedback");
    expect(source).toContain("actuatorCommandAvailability");
    expect(source).toContain("Đang chờ thiết bị phản hồi");
  });
});
