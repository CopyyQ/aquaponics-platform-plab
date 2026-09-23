export type ActuatorCommandAvailabilityInput = {
  connectionStatus: string;
  isEnabled: boolean;
  commandPending: boolean;
  desiredState: boolean | null;
  reportedState: boolean | null;
  hasActiveAlert: boolean;
};

export type ActuatorCommandAvailability =
  | { allowed: true; reason: null }
  | {
      allowed: false;
      reason: "DEVICE_OFFLINE" | "ACTUATOR_DISABLED" | "COMMAND_PENDING";
    };

export function actuatorCommandAvailability({
  connectionStatus,
  isEnabled,
  commandPending,
}: ActuatorCommandAvailabilityInput): ActuatorCommandAvailability {
  if (!isEnabled) {
    return { allowed: false, reason: "ACTUATOR_DISABLED" };
  }
  if (connectionStatus !== "ONLINE") {
    return { allowed: false, reason: "DEVICE_OFFLINE" };
  }
  if (commandPending) {
    return { allowed: false, reason: "COMMAND_PENDING" };
  }

  // desired/reported mismatch and electrical alerts are diagnostics, not
  // command interlocks. The operator may retry/reassert a command while those
  // warnings remain visible.
  return { allowed: true, reason: null };
}
