import type { ProjectScenarioSummary } from "@/api/contracts"

export function applyProjectScenarioActivation(
  current: ProjectScenarioSummary[] | undefined,
  activated: ProjectScenarioSummary
): ProjectScenarioSummary[] | undefined {
  if (!current) return current

  return current.map((scenario) => {
    if (scenario.id === activated.id) return activated
    if (!scenario.is_active) return scenario
    return { ...scenario, is_active: false }
  })
}
