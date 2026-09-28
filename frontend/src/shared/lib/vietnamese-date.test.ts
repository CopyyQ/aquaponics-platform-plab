import { describe, expect, it } from "vitest"
import { formatVietnamClock, formatVietnamDate, msUntilNextMinute } from "./date"

describe("Date and clock on the header", () => {
  it("writes the date with leading zeros, the way the design shows it", () => {
    // 08:45 ngày 26/09/2026 giờ Việt Nam = 01:45 UTC
    const at = new Date("2026-09-26T01:45:00Z")

    expect(formatVietnamDate(at)).toBe("26/09/2026")
    expect(formatVietnamClock(at)).toBe("08:45")
  })

  it("rolls over the day, month and year", () => {
    expect(formatVietnamDate(new Date("2026-09-29T03:00:00Z"))).toBe("29/09/2026")
    expect(formatVietnamDate(new Date("2026-10-01T03:00:00Z"))).toBe("01/10/2026")
    expect(formatVietnamDate(new Date("2027-01-01T03:00:00Z"))).toBe("01/01/2027")
  })

  it("reads the clock in Vietnam time, not the browser time zone", () => {
    // 17:30 UTC ngày 28 đã là 00:30 ngày 29 ở Việt Nam
    const at = new Date("2026-09-28T17:30:00Z")

    expect(formatVietnamDate(at)).toBe("29/09/2026")
    expect(formatVietnamClock(at)).toBe("00:30")
  })

  it("keeps midnight at 00 instead of 24", () => {
    expect(formatVietnamClock(new Date("2026-09-28T17:00:00Z"))).toBe("00:00")
  })

  it("wakes up exactly on the next minute", () => {
    expect(msUntilNextMinute(new Date("2026-09-26T01:45:00.000Z"))).toBe(60_000)
    expect(msUntilNextMinute(new Date("2026-09-26T01:45:59.500Z"))).toBe(500)
  })

  it("never schedules a wake-up in the past", () => {
    for (const second of [0, 1, 30, 59]) {
      const at = new Date(`2026-09-26T01:45:${String(second).padStart(2, "0")}.000Z`)

      expect(msUntilNextMinute(at)).toBeGreaterThan(0)
      expect(msUntilNextMinute(at)).toBeLessThanOrEqual(60_000)
    }
  })
})
