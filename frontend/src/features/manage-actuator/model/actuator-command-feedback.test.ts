import { describe, expect, it, vi } from "vitest";
import { waitForActuatorCommandFeedback } from "./actuator-command-feedback";

describe("waitForActuatorCommandFeedback", () => {
  it("chỉ thành công sau ACK đúng trạng thái thiết bị", async () => {
    const readCommands = vi
      .fn()
      .mockResolvedValueOnce([
        { command_id: 21, status: "PUBLISHED", reported_state: null },
      ])
      .mockResolvedValueOnce([
        { command_id: 21, status: "ACKNOWLEDGED", reported_state: true },
      ]);

    const result = await waitForActuatorCommandFeedback({
      commandId: 21,
      desiredState: true,
      readCommands,
      pollIntervalMs: 0,
      timeoutMs: 1000,
    });

    expect(result.status).toBe("ACKNOWLEDGED");
    expect(result.reported_state).toBe(true);
    expect(readCommands).toHaveBeenCalledTimes(2);
  });

  it("báo lỗi khi thiết bị trả FAILED", async () => {
    await expect(
      waitForActuatorCommandFeedback({
        commandId: 22,
        desiredState: false,
        readCommands: async () => [
          { command_id: 22, status: "FAILED", reported_state: true },
        ],
        pollIntervalMs: 0,
        timeoutMs: 1000,
      }),
    ).rejects.toThrow("Thiết bị báo thực thi lệnh thất bại");
  });

  it("không coi ACK sai reported_state là thành công", async () => {
    await expect(
      waitForActuatorCommandFeedback({
        commandId: 23,
        desiredState: true,
        readCommands: async () => [
          { command_id: 23, status: "ACKNOWLEDGED", reported_state: false },
        ],
        pollIntervalMs: 0,
        timeoutMs: 1000,
      }),
    ).rejects.toThrow("trạng thái phản hồi không khớp");
  });
});
