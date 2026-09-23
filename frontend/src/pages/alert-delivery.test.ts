import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

describe("Alert delivery page contract", () => {
  it("keeps the operator UI focused on Telegram, recipients, and history", () => {
    const source = readFileSync(new URL("./alert-delivery.tsx", import.meta.url), "utf8")

    expect(source).toContain("Telegram cảnh báo")
    expect(source).toContain("Người nhận Telegram")
    expect(source).toContain("Lịch sử Telegram")
    expect(source).toContain("Chống spam tự động")
    expect(source).toContain("Báo khi hệ thống trở lại bình thường")

    expect(source).not.toContain("Chính sách theo mức rủi ro")
    expect(source).not.toContain("Generation hiện tại")
    expect(source).not.toContain("risk_policies")
    expect(source).not.toContain("notify_on_escalation")
    expect(source).not.toContain("notify_alert_reminder")
  })
})
