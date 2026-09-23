import { describe, expect, it } from "vitest";
import { actuatorCommandAvailability } from "./actuator-control-policy";

describe("actuatorCommandAvailability", () => {
  it("cho phep dieu khien khi actuator online du trang thai chua dong bo va co canh bao dien", () => {
    expect(
      actuatorCommandAvailability({
        connectionStatus: "ONLINE",
        isEnabled: true,
        commandPending: false,
        desiredState: true,
        reportedState: false,
        hasActiveAlert: true,
      }),
    ).toEqual({ allowed: true, reason: null });
  });

  it("chi khoa khi actuator bi vo hieu hoa, device khong online hoac dang co lenh cho phan hoi", () => {
    expect(
      actuatorCommandAvailability({
        connectionStatus: "OFFLINE",
        isEnabled: true,
        commandPending: false,
        desiredState: true,
        reportedState: false,
        hasActiveAlert: false,
      }).allowed,
    ).toBe(false);
    expect(
      actuatorCommandAvailability({
        connectionStatus: "ONLINE",
        isEnabled: false,
        commandPending: false,
        desiredState: true,
        reportedState: false,
        hasActiveAlert: false,
      }).allowed,
    ).toBe(false);
    expect(
      actuatorCommandAvailability({
        connectionStatus: "ONLINE",
        isEnabled: true,
        commandPending: true,
        desiredState: true,
        reportedState: false,
        hasActiveAlert: false,
      }).allowed,
    ).toBe(false);
  });

  it("khong khoa lenh lap lai chi vi reported state da trung voi lenh", () => {
    expect(
      actuatorCommandAvailability({
        connectionStatus: "ONLINE",
        isEnabled: true,
        commandPending: false,
        desiredState: true,
        reportedState: true,
        hasActiveAlert: true,
      }).allowed,
    ).toBe(true);
  });
});
