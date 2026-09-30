import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { ScadaIssue } from "@/api/contracts"
import { OperatorDeviceIssuesBoard } from "./OperatorDeviceIssuesBoard"

function issue(overrides: Partial<ScadaIssue> = {}): ScadaIssue {
  return {
    id: "actuator-10-timeout",
    severity: "CRITICAL",
    title: "Bơm bể lọc vi sinh không phản hồi lệnh",
    root_cause: "Lệnh gần nhất: TIMEOUT",
    affected_entities: ["Thiết bị", "Bơm bể lọc vi sinh"],
    current_state: "Mong muốn: true; thực tế: false.",
    timestamp: "2026-09-24T09:13:35Z",
    suggested_action: "Kiểm tra kết nối Device và cơ cấu chấp hành trước khi gửi lại lệnh.",
    device_id: "dev-1",
    sensor_id: null,
    actuator_id: "act-10",
    ...overrides,
  }
}

function render(issues: ScadaIssue[]) {
  return renderToStaticMarkup(<OperatorDeviceIssuesBoard issues={issues} />)
}

describe("OperatorDeviceIssuesBoard", () => {
  it("vanishes entirely when nothing is wrong", () => {
    expect(render([])).toBe("")
  })

  it("names the fault, its cause and what to do", () => {
    const markup = render([issue()])
    expect(markup).toContain("Bơm bể lọc vi sinh không phản hồi lệnh")
    expect(markup).toContain("Lệnh gần nhất: TIMEOUT")
    expect(markup).toContain("Kiểm tra kết nối Device")
  })

  it("warns that these are not recorded, so nobody waits for them in the history", () => {
    expect(render([issue()])).toContain("không được lưu thành bản ghi")
  })

  it("offers no action, because none of these can be acted on here", () => {
    const markup = render([issue()])
    expect(markup).not.toContain("<button")
    expect(markup).not.toContain("Xác nhận")
  })

  it("tones a critical fault red and a warning amber", () => {
    expect(render([issue()])).toContain("bg-rose-50")
    expect(render([issue({ severity: "WARNING" })])).toContain("bg-amber-50")
  })
})
