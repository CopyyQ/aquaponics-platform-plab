import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { ProjectScenarioCard } from "@/features/manage-project-scenarios/components/ProjectScenarioList"
import type { ProjectScenarioSummary } from "@/api/contracts"

const scenario = (active: boolean): ProjectScenarioSummary => ({
  id: active ? "active-id" : "inactive-id",
  name: active ? "Kịch bản mặc định" : "Kịch bản mùa nóng",
  description: active ? "Đang vận hành" : "Cho mùa nóng",
  is_active: active,
  sensor_count: 12,
  actuator_count: 8,
  source_scenario_catalog_id: 1,
  cloned_from_scenario_id: null,
  created_at: "2026-09-23T00:00:00Z",
  updated_at: "2026-09-23T00:00:00Z",
})

const renderCard = (active: boolean) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <ProjectScenarioCard
        scenario={scenario(active)}
        systemId="system"
        deviceId="device"
        canCreate
        canUpdate
        canDelete
        canActivate
        onClone={() => undefined}
        onEdit={() => undefined}
        onDelete={() => undefined}
        onActivate={() => undefined}
      />
    </MemoryRouter>,
  )

describe("ProjectScenarioList", () => {
  it("shows active state without delete/use action", () => {
    const markup = renderCard(true)
    expect(markup).toContain("ĐANG SỬ DỤNG")
    expect(markup).toContain("Kịch bản mặc định")
    expect(markup).toContain("12 cảm biến")
    expect(markup).toContain("8 cơ cấu chấp hành")
    expect(markup).not.toContain(">Sử dụng<")
    expect(markup).not.toContain(">Xóa<")
  })

  it("offers lifecycle actions for an inactive scenario", () => {
    const markup = renderCard(false)
    expect(markup).toContain("Kịch bản mùa nóng")
    expect(markup).toContain(">Mở<")
    expect(markup).toContain(">Nhân bản<")
    expect(markup).toContain(">Sử dụng<")
    expect(markup).toContain(">Xóa<")
  })

  it("replaces the deprecated per-resource scenario panel on Device page", () => {
    const page = readFileSync(
      resolve(process.cwd(), "src/pages/device-detail-activation.tsx"),
      "utf8",
    )
    expect(page).toContain("ProjectScenarioList")
    expect(page).not.toContain("RuntimeScenarioPanel")
    expect(page).not.toContain("getDeviceRuntimeScenarios")
    expect(page).not.toContain("Kịch bản cảm biến")
    expect(page).not.toContain("Kịch bản cơ cấu chấp hành")
  })
})
