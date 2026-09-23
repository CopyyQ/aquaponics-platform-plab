import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

describe("AuditLogsPage notification guidance", () => {
  it("describes the canonical Telegram lifecycle without retired escalation or reminders", () => {
    const source = readFileSync(new URL("./AuditLogsPage.tsx", import.meta.url), "utf8")

    expect(source).toContain("cảnh báo mới")
    expect(source).toContain("trở lại bình thường")
    expect(source).not.toContain("tăng mức, nhắc lại")
  })
})
