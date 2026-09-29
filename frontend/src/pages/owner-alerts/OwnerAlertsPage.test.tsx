import { describe, expect, it } from "vitest"
import { OWNER_ALERT_FILTERS, parseOwnerAlertFilter } from "./OwnerAlertsPage"

describe("Owner alert filter", () => {
  it("opens on the unresolved list when the diagram sends the owner here to act", () => {
    expect(parseOwnerAlertFilter("OPEN")).toBe("OPEN")
  })

  it("shows everything when no filter is asked for", () => {
    expect(parseOwnerAlertFilter(null)).toBe("ALL")
    expect(parseOwnerAlertFilter("")).toBe("ALL")
  })

  it("falls back to everything rather than an empty screen on a bad link", () => {
    // Đường dẫn hỏng thì thà hiện thừa còn hơn hiện trắng
    expect(parseOwnerAlertFilter("open")).toBe("ALL")
    expect(parseOwnerAlertFilter("PENDING")).toBe("ALL")
    expect(parseOwnerAlertFilter("<script>")).toBe("ALL")
  })

  it("offers plain wording instead of raw lifecycle codes", () => {
    expect(OWNER_ALERT_FILTERS.map((item) => item.label)).toEqual([
      "Tất cả trạng thái",
      "Chưa xử lý",
      "Đã xử lý",
    ])
    for (const item of OWNER_ALERT_FILTERS) expect(parseOwnerAlertFilter(item.value)).toBe(item.value)
  })
})
