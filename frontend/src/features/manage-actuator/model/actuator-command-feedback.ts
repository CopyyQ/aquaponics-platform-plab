export interface ActuatorCommandFeedback {
  command_id: number;
  status: string;
  reported_state: boolean | null;
}

interface WaitForActuatorCommandFeedbackOptions {
  commandId: number;
  desiredState: boolean;
  readCommands: () => Promise<ActuatorCommandFeedback[]>;
  timeoutMs?: number;
  pollIntervalMs?: number;
}

const FAILED_STATUSES = new Set(["FAILED", "TIMEOUT"]);

function sleep(milliseconds: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

export async function waitForActuatorCommandFeedback({
  commandId,
  desiredState,
  readCommands,
  timeoutMs = 50_000,
  pollIntervalMs = 400,
}: WaitForActuatorCommandFeedbackOptions): Promise<ActuatorCommandFeedback> {
  const startedAt = Date.now();

  while (Date.now() - startedAt <= timeoutMs) {
    const commands = await readCommands();
    const command = commands.find((item) => item.command_id === commandId);

    if (command?.status === "ACKNOWLEDGED") {
      if (command.reported_state !== desiredState) {
        throw new Error("Thiết bị đã ACK nhưng trạng thái phản hồi không khớp yêu cầu.");
      }
      return command;
    }

    if (command && FAILED_STATUSES.has(command.status)) {
      throw new Error(
        command.status === "TIMEOUT"
          ? "Quá thời gian chờ thiết bị phản hồi."
          : "Thiết bị báo thực thi lệnh thất bại.",
      );
    }

    await sleep(pollIntervalMs);
  }

  throw new Error("Quá thời gian chờ thiết bị phản hồi.");
}
