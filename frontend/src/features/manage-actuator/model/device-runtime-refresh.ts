export const DEVICE_RUNTIME_REFETCH_MS = 2000

export type ActuatorCommandVariables = {
  actuatorId: string
  desiredState: boolean
}

export function runtimeRefetchInterval(
  visibilityState: DocumentVisibilityState,
): number | false {
  return visibilityState === "visible" ? DEVICE_RUNTIME_REFETCH_MS : false
}

export function isActuatorCommandPendingFor(
  isPending: boolean,
  variables: ActuatorCommandVariables | undefined,
  actuatorId: string,
): boolean {
  return isPending && variables?.actuatorId === actuatorId
}
