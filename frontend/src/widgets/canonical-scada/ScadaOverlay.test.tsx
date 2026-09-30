import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { SCADA_CARDS, SCADA_IMAGE_ASPECT, SCADA_LEVEL_GAUGE } from "@/entities/scada/model/scada-cards"
import { ScadaOverlay } from "./ScadaOverlay"

type OverlaySource = Parameters<typeof ScadaOverlay>[0]["runtime"]

// name đặt như tên thật trong cơ sở dữ liệu, không lấy mã làm tên: hộp chi tiết lấy
// thẳng tên này nên dữ liệu giả dùng mã sẽ che mất lỗi rò mã ra màn hình.
function sensor(id: string, code: string, unit: string, name: string) {
  return { id, code, name, sensor_model_code: code, unit, device_id: "dev-1", enabled: true }
}
function value(id: string, v: number) {
  return { id, value: v, recorded_at: "2026-09-25T04:40:00Z", received_at: "2026-09-25T04:40:01Z", freshness: "FRESH", quality: "VALID", quality_reason: null }
}

function render(runtime: OverlaySource) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ScadaOverlay runtime={runtime} localHour={9} />
    </MemoryRouter>,
  )
}

function source(): OverlaySource {
  return {
    aquaponics_system: { id: "sys-1", code: "AQS-1", name: "Hệ thống", status: "ACTIVE" },
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: 1, template_code: "T", enabled: true, connectivity: "ONLINE", last_seen_at: null }],
      sensors: [
        sensor("s-level", "WATER_LEVELW2", "%", "Cảm biến mực nước bể cá"),
        sensor("s-temp", "WATER_TEMPERATURE", "°C", "Cảm biến nhiệt độ nước"),
        sensor("s-ph", "PH", "pH", "Cảm biến pH"),
        sensor("s-air", "AIR_TEMPERATURE", "°C", "Cảm biến nhiệt độ không khí"),
        sensor("s-volt", "VOLTAGE", "V", "Cảm biến điện áp"),
        sensor("s-curr", "CURRENT", "A", "Cảm biến dòng điện"),
      ],
      actuators: [{ id: "a-pump", code: "FISH_TANK_PUMP", name: "Bơm bể cá", actuator_model_code: "FISH_TANK_PUMP", device_id: "dev-1", enabled: true }],
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity: "ONLINE", last_seen_at: null }],
      sensors: [value("s-level", 100), value("s-temp", 28.7), value("s-ph", 6.8), value("s-air", 32.5), value("s-volt", 12), value("s-curr", 2)],
      actuators: [{ id: "a-pump", desired_state: true, reported_state: true, synchronization: "IN_SYNC", command_status: "ACKED", command_time: null, last_ack_at: "2026-09-25T04:40:00Z", failure_reason: null }],
      alerts: [],
    },
    issues: [],
    updated_at: "2026-09-25T04:40:01Z",
  } as unknown as OverlaySource
}

function withLevel(level: number): OverlaySource {
  const base = source()
  return {
    ...base,
    runtime: {
      ...base.runtime,
      sensors: base.runtime.sensors.map((s) => (s.id === "s-level" ? { ...s, value: level } : s)),
    },
  } as unknown as OverlaySource
}

function withIssue(): OverlaySource {
  const base = source()
  return {
    ...base,
    issues: [{
      id: "sensor-ph-alert",
      severity: "CRITICAL",
      title: "pH nước vượt ngưỡng",
      root_cause: "Cảm biến pH",
      affected_entities: ["Cảm biến pH"],
      current_state: "6.8",
      timestamp: "2026-09-25T04:00:00Z",
      suggested_action: "Kiểm tra hệ đệm pH",
      device_id: "dev-1",
      sensor_id: "s-ph",
      actuator_id: null,
    }],
  } as unknown as OverlaySource
}

describe("ScadaOverlay", () => {
  const markup = render(source())

  it("draws the scenario image behind the overlay", () => {
    expect(markup).toContain("/scada/scenarios/feeder-closed_tank-100_morning.jpg")
    expect(markup).toContain("scada-overlay")
  })

  it("puts live values on their calibrated cards", () => {
    expect(markup).toContain("Bể cá")
    expect(markup).toContain("28,7 °C")
    expect(markup).toContain("6,8 pH")
    // Cảm biến không khí đã rời sơ đồ khi thẻ này nhường chỗ cho tình trạng hệ thống
    expect(markup).not.toContain("32,5 °C")
  })

  it("shows derived power on the cabinet meter", () => {
    expect(markup).toContain("24 W")
  })

  it("leaves uninstrumented meters blank instead of inventing a number", () => {
    expect(markup).toContain("—")
  })

  it("shows nothing but the diagram itself so the screen never scrolls", () => {
    expect(markup).not.toContain("Thiết bị khác")
  })

  it("caps the frame width by the available height so it fits one screen", () => {
    expect(markup).toContain(`calc((100dvh - 7.5rem) * ${SCADA_IMAGE_ASPECT})`)
  })

  it("shapes the frame to the artwork so no letterbox shifts the calibrated coordinates", () => {
    expect(markup).toContain(`aspect-ratio:${SCADA_IMAGE_ASPECT}`)
  })

  // Suy từ chính toạ độ đã hiệu chỉnh thay vì chép số vào đây: hiệu chỉnh lại
  // ảnh nền là chuyện thường, mà cách neo thẻ thì không được đổi theo.
  function card(id: string) {
    const found = SCADA_CARDS.find((item) => item.id === id)
    if (!found) throw new Error(`Thiếu thẻ ${id}`)
    return found
  }

  it("grows cards placed above equipment upward so they never cover the drawing", () => {
    for (const id of ["biofilter", "water-supply"]) {
      const { box } = card(id)
      expect(card(id).anchor).toBe("bottom")
      expect(markup).toContain(`bottom:${100 - (box.y + box.h)}%`)
    }
  })

  it("still anchors cards drawn over their subject by the top edge", () => {
    expect(card("fish-tank").anchor).toBeUndefined()
    expect(markup).toContain(`top:${card("fish-tank").box.y}%`)
  })

  it("pins a label to the middle of its box so wide text still points at the right part", () => {
    // Nhãn ghim vào van: chữ rộng hơn khung nên phải dịch lại nửa chính nó,
    // nếu không tâm chữ sẽ lệch sang phải khỏi cái van đã canh.
    const { box } = card("fresh-water-valve")
    expect(card("fresh-water-valve").centered).toBe(true)
    expect(markup).toContain(`left:${box.x + box.w / 2}%`)
    expect(markup).toContain(`top:${box.y + box.h / 2}%`)
    expect(markup).toContain("translate(-50%, -50%)")
  })

  it("keeps a pinned valve label free of its reading until the card is opened", () => {
    const face = markup.slice(markup.indexOf("Van cấp nước"))
    expect(face.slice(0, 400)).not.toContain("TẮT")
    expect(face.slice(0, 400)).not.toContain("chỉ số")
  })

  it("shows only the leading metrics on the card face and hides the rest behind a click", () => {
    // Chỉ xét phần lớp phủ, danh sách dự phòng cho màn nhỏ vẫn liệt kê đủ
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))

    expect(overlay).toContain("+2 chỉ số")
    // Lời mời bấm nằm ở aria-label, không chiếm chỗ trên mặt thẻ vốn đã chật
    expect(overlay).not.toContain("chỉ số · bấm để xem")
    expect(overlay).toContain("Bấm để xem chi tiết")
    // Oxy hòa tan là chỉ số thứ ba của thẻ Bể cá nên không nằm ngoài mặt thẻ
    expect(overlay).not.toContain("Oxy hòa tan")
  })

  it("marks a healthy group green and a group with a backend issue red", () => {
    // Huy hiệu giữ màu nhận diện xanh dương ở mọi trạng thái
    expect(markup).toContain("bg-sky-500")
    expect(render(withIssue())).toContain("bg-sky-500")
    // Tình trạng báo bằng chấm riêng đứng sau tên thẻ
    expect(markup).toContain("bg-emerald-500")
    // Mức nghiêm trọng đổi hẳn sang tam giác cảnh báo nên không còn chấm đỏ
    expect(render(withIssue())).toContain("lucide-triangle-alert")
    expect(render(withIssue())).not.toContain("bg-rose-500")
  })

  it("keeps a round dot for every severity below critical", () => {
    // Chỉ mức nghiêm trọng mới đổi hình; mức nhẹ hơn vẫn là chấm tròn
    expect(markup).not.toContain("lucide-triangle-alert")
    expect(markup).toContain("rounded-full")
  })

  it("draws no connector lines between cards and equipment", () => {
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))

    expect(overlay).not.toContain("<polyline")
    expect(overlay).not.toContain("non-scaling-stroke")
  })

  it("never leaks raw sensor codes into text the owner reads", () => {
    for (const code of ["FRESH_WATER_VALVE", "WATER_LEVELW2", "AIR_TEMPERATURE", "TDS"]) {
      expect(markup).not.toContain(`>${code}<`)
      expect(markup).not.toContain(`${code} ·`)
    }
  })

  it("gives a narrow card a full line for its label instead of clipping it", () => {
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))

    // Thẻ Bể cá xếp dọc nên nhãn không bị cắt cụt thành "Nhi..."
    expect(overlay).toContain("Nhiệt độ nước")
    expect(overlay).toContain("flex-col")
  })

  it("states system health in plain words instead of raw metrics", () => {
    expect(markup).toContain("Tình trạng hệ thống")
    expect(render(withIssue())).toContain("Hệ thống có vấn đề")
  })

  it("keeps every card title on a single line", () => {
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))

    for (const title of ["Tình trạng hệ thống", "Bể lọc vi sinh", "Bể cá"]) {
      expect(overlay).toContain(`<span class="whitespace-nowrap">${title}</span>`)
    }
  })

  it("shows the exact water level on the gauge, not the two-step picture value", () => {
    // Ảnh nền làm tròn 73% thành bản vẽ 60%; cột đo phải giữ đúng con số thật
    const markup73 = render(withLevel(73))

    expect(markup73).toContain("feeder-closed_tank-60_morning.jpg")
    expect(markup73).toContain("73%")
    expect(markup73).toContain("height:73%")
  })

  it("swaps the gauge label between full and not full, never showing both", () => {
    const full = render(withLevel(95))
    const low = render(withLevel(42))

    expect(full).toContain(">Full<")
    expect(full).not.toContain(">Thiếu<")

    expect(low).toContain(">Thiếu<")
    expect(low).not.toContain(">Full<")
  })

  it("pins the gauge tick to the water surface, not to a fixed spot", () => {
    // Nước 42% thì mặt nước nằm 58% tính từ đỉnh ống
    expect(render(withLevel(42))).toContain("top:58%")
    // Nước 95% thì vạch gần sát đỉnh
    expect(render(withLevel(95))).toContain("top:5%")
  })

  it("draws the gauge scale over the whole tube and names the level", () => {
    expect(markup).toContain("Mực nước")
    // Vạch kẻ dài đúng bằng cột, không cắt ngắn
    expect(markup).toContain("h-full w-[0.09em]")
  })

  it("keeps the gauge tube exactly on the calibrated box beside the tank", () => {
    // Khung đúng toạ độ đã hiệu chỉnh: cao bằng bể, sát cạnh phải.
    // Nhãn và vạch chia nằm ngoài ống nên không nới khung này ra.
    const { x, y, w, h } = SCADA_LEVEL_GAUGE.box
    expect(markup).toContain(`left:${x}%;top:${y}%;width:${w}%;height:${h}%`)
    // Giá trị bằng chữ vẫn đọc được cho trình đọc màn hình
    expect(markup).toContain("Mực nước bể cá: 100 %")
  })

  it("clamps the fill so an out-of-range reading never overflows the tube", () => {
    expect(render(withLevel(140))).toContain("height:100%")
    expect(render(withLevel(-5))).toContain("height:0%")
  })

  it("sizes the system card to its text instead of a fixed width", () => {
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))

    expect(overlay).toContain("w-max")
    // Không còn thuộc tính width cố định cho thẻ này
    expect(overlay).not.toContain("left:1.54%;top:2.41%;width")
  })

  it("frames only the system card, leaving metric cards bare on the drawing", () => {
    const overlay = markup.slice(0, markup.indexOf('class="lg:hidden"'))
    const framed = overlay.split("bg-white/95").length - 1

    expect(framed).toBe(1)
  })

  it("offers a way to act only when something is actually wrong", () => {
    const broken = render(withIssue())

    expect(broken).toContain("Kiểm tra ngay")
    // Mở thẳng danh sách chưa xử lý, không bắt người dùng tự lọc
    expect(broken).toContain("/aquaponics-systems/sys-1/alerts?status=OPEN")
  })

  it("keeps every metric readable on small screens through the fallback list", () => {
    expect(markup).toContain("Thông số trên sơ đồ")
  })
})
