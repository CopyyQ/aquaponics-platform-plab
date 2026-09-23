import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import type { ProjectScenarioItem } from "@/api/contracts"
import {
  ProjectScenarioBranchForm,
  buildActuatorCondition,
  buildSensorCondition,
} from "@/features/manage-project-scenarios/components/ProjectScenarioBranchDialog"
import { ProjectScenarioResourceGroup } from "@/features/manage-project-scenarios/components/ProjectScenarioResourceGroup"

const sensorItem: ProjectScenarioItem = {
  id: "item-sensor",
  target_type: "SENSOR",
  resource: {
    id: "sensor",
    code: "PH-01",
    name: "pH bể cá",
    model_id: 1,
    is_enabled: true,
  },
  name: "pH bể cá",
  is_enabled: true,
  branches: [],
}

describe("ProjectScenario detail editor", () => {
  it("shows every resource even when it has no branches and respects read-only mode", () => {
    const readOnly = renderToStaticMarkup(
      <ProjectScenarioResourceGroup
        title="Cảm biến"
        items={[sensorItem]}
        canWrite={false}
        onAdd={() => undefined}
        onEdit={() => undefined}
        onDelete={() => undefined}
      />,
    )
    expect(readOnly).toContain("pH bể cá")
    expect(readOnly).toContain("Chưa cấu hình")
    expect(readOnly).not.toContain("Thêm nhánh")

    const writable = renderToStaticMarkup(
      <ProjectScenarioResourceGroup
        title="Cảm biến"
        items={[sensorItem]}
        canWrite
        onAdd={() => undefined}
        onEdit={() => undefined}
        onDelete={() => undefined}
      />,
    )
    expect(writable).toContain("Thêm nhánh")
  })

  it("builds canonical Sensor threshold and range conditions", () => {
    expect(
      buildSensorCondition({
        mode: "THRESHOLD",
        operator: "GT",
        threshold: "7.2",
        min: "",
        max: "",
      }),
    ).toEqual({ evaluatorType: "THRESHOLD", condition: { operator: "GT", value: 7.2 } })

    expect(
      buildSensorCondition({
        mode: "RANGE",
        operator: "GT",
        threshold: "",
        min: "6.5",
        max: "8",
      }),
    ).toEqual({
      evaluatorType: "RANGE_BANDS",
      condition: {
        range_mode: "OUTSIDE_RANGE",
        range: { min: 6.5, max: 8 },
      },
    })
  })

  it("builds one coherent Actuator condition from state and electrical evidence", () => {
    expect(
      buildActuatorCondition({
        desiredState: "ON",
        reportedState: "OFF",
        voltageMin: "11",
        voltageMax: "13",
        currentMin: "",
        currentMax: "0.2",
      }),
    ).toEqual({
      logic: "AND",
      desired_state: true,
      reported_state: false,
      voltage: { min: 11, max: 13 },
      current: { min: null, max: 0.2 },
    })
  })

  it("renders all operational and Telegram fields in the branch form", () => {
    const markup = renderToStaticMarkup(
      <ProjectScenarioBranchForm
        targetType="SENSOR"
        initialBranch={null}
        pending={false}
        error={null}
        onCancel={() => undefined}
        onSubmit={() => undefined}
      />,
    )
    for (const label of [
      "Tên nhánh",
      "Điều kiện",
      "Thời gian duy trì",
      "Mức rủi ro",
      "Bật nhánh",
      "Nội dung cảnh báo Telegram",
      "Ảnh hưởng",
      "Hành động khuyến nghị",
    ]) {
      expect(markup).toContain(label)
    }
  })
})
