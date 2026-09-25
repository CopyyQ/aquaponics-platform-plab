import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

import { nextBranchIndex, scenarioItemMatches } from "./catalog-hub"
import type { ScenarioCatalogBranch, ScenarioCatalogItem } from "@/api/contracts"

function branch(key: string): ScenarioCatalogBranch {
  return {
    key,
    label: key,
    enabled: true,
    evaluator_type: "THRESHOLD",
    condition_config: { operator: "LT", value: 0, severity: "WARNING", duration_seconds: 0 },
    risk_level: "MEDIUM",
    message: null,
    consequence: null,
    recommended_action: null,
  }
}

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("scenario branch key allocation", () => {
  it("numbers a new sensor branch after the existing ones", () => {
    expect(nextBranchIndex("SENSOR", [branch("SENSOR_RULE_1")])).toBe(2)
  })

  it("skips indexes already taken so a deleted middle branch cannot collide", () => {
    const branches = [branch("SENSOR_RULE_1"), branch("SENSOR_RULE_3")]
    expect(nextBranchIndex("SENSOR", branches)).toBe(4)
  })

  it("keeps actuator keys separate from sensor keys", () => {
    expect(nextBranchIndex("ACTUATOR", [branch("SENSOR_RULE_1"), branch("SENSOR_RULE_2")])).toBe(3)
    expect(nextBranchIndex("ACTUATOR", [])).toBe(1)
  })
})

function item(overrides: Partial<ScenarioCatalogItem> = {}): ScenarioCatalogItem {
  return {
    id: 1,
    target_type: "SENSOR",
    resource_code: "WATER_TEMPERATURE",
    model_code: "DS18B20",
    model_name: "Cảm biến nhiệt độ nước",
    name: "Cảm biến nhiệt độ nước",
    is_enabled: true,
    notes: null,
    source_reference: "tài liệu",
    branches: [],
    ...overrides,
  } as ScenarioCatalogItem
}

describe("scenario resource search", () => {
  it("keeps every resource when the box is empty or blank", () => {
    expect(scenarioItemMatches(item(), "")).toBe(true)
    expect(scenarioItemMatches(item(), "   ")).toBe(true)
  })

  it("matches on name, resource code and model, ignoring case", () => {
    expect(scenarioItemMatches(item(), "nhiệt độ")).toBe(true)
    expect(scenarioItemMatches(item(), "water_temperature")).toBe(true)
    expect(scenarioItemMatches(item(), "ds18b20")).toBe(true)
  })

  it("rejects a resource that matches nothing", () => {
    expect(scenarioItemMatches(item(), "bơm")).toBe(false)
  })

  it("finds actuators too", () => {
    const pump = item({ target_type: "ACTUATOR", resource_code: "FISH_TANK_PUMP", model_code: "IRRIGATION_PUMP", model_name: "Bơm tưới", name: "Bơm bể cá" })
    expect(scenarioItemMatches(pump, "bơm bể")).toBe(true)
  })
})

describe("scenario catalog list", () => {
  it("filters resources by status from inside the catalog card", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain('<SelectItem value="ALL">Tất cả trạng thái</SelectItem>')
    expect(catalog).toContain('<SelectItem value="ACTIVE">Đang hoạt động</SelectItem>')
    expect(catalog).toContain('<SelectItem value="DISABLED">Đã vô hiệu hóa</SelectItem>')
    expect(catalog).toContain('status === "ALL" || (status === "ACTIVE" ? item.is_enabled : !item.is_enabled)')
  })

  it("filters scenario catalogs by status next to the page search", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain('aria-label="Lọc kịch bản theo trạng thái"')
    expect(catalog).toContain('<SelectItem value="ALL">Tất cả kịch bản</SelectItem>')
    expect(catalog).toContain('catalogStatus === "ALL" || (catalogStatus === "ACTIVE" ? catalog.is_active : !catalog.is_active)')
  })

  it("orders the card controls as status, filter, edit, delete", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toMatch(/<StatusBadge[^>]*value={catalog\.is_active[\s\S]{0,200}<Select value={status}[\s\S]{0,900}<Pencil \/>Sửa bộ<\/Button>[\s\S]{0,300}<Trash2 \/>Xóa<\/Button>/)
  })

  it("expands both groups while searching or filtering", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain('open={searching || status !== "ALL" || groupsOpen.sensor}')
    expect(catalog).toContain('open={searching || status !== "ALL" || groupsOpen.actuator}')
  })

  it("keeps a distinct empty state for a device with no scenarios", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("Không tìm thấy cảm biến hoặc cơ cấu chấp hành")
    expect(catalog).toContain("Chưa có kịch bản cho thiết bị")
  })
})

describe("scenario resource groups collapse", () => {
  it("hides sensors and actuators behind their own toggle, closed by default", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("useState({ sensor: false, actuator: false })")
    expect(catalog).toContain("aria-expanded={open}")
    expect(catalog).toContain("sensor: !current.sensor")
    expect(catalog).toContain("actuator: !current.actuator")
  })
})

describe("scenario branch editing opens a modal", () => {
  it("lists branches as summary rows and edits them in a nested dialog", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("function BranchSummaryRow")
    expect(catalog).toContain("function BranchDialog")
    expect(catalog).toContain("Thêm nhánh điều kiện")
    expect(catalog).toContain("Sửa nhánh điều kiện")
    expect(catalog).toContain("onClick={openBranchCreate}")
    expect(catalog).toContain("đã được dùng cho nhánh khác")
  })

  it("confirms before adding a branch and reports success for 4 seconds", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("Bạn có muốn thêm nhánh này không?")
    expect(catalog).toContain("<AlertDialogCancel>Hủy</AlertDialogCancel>")
    expect(catalog).toContain("<AlertDialogAction onClick={submit}>Xác nhận</AlertDialogAction>")
    expect(catalog).toContain('toast.success("Thêm nhánh thành công", { duration: 4000 })')
  })

  it("confirms before removing a branch instead of deleting on the first click", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("onDelete={() => setDeletingBranch(index)}")
    expect(catalog).toContain("Xóa nhánh {branchPendingDelete?.label.trim() || branchPendingDelete?.key}?")
    expect(catalog).toContain('<AlertDialogAction variant="destructive" onClick={removeBranch}>Xóa</AlertDialogAction>')
    expect(catalog).not.toContain("onDelete={() => setBranches((current) => current.filter((_, i) => i !== index))}")
  })

  it("asks for confirmation only when adding, not when editing an existing branch", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("if (draft.index === null) setConfirmOpen(true); else submit()")
    expect(catalog).toContain("if (draft.index === null) toast.success")
  })
})
