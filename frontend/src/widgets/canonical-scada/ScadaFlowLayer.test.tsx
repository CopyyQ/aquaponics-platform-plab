import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { SCADA_METRICS } from "@/entities/scada/model/scada-cards"
import { SCADA_FLOWS, polylineLength, type ScadaFlow } from "@/entities/scada/model/scada-flows"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { ScadaFlowLayer, arrowCount, isFlowing } from "./ScadaFlowLayer"

/** Mọi cơ cấu mà bố cục mạch nhắc tới, để bài kiểm thử vẽ được đủ đường ống. */
const WIRED = [...new Set(SCADA_FLOWS.map((flow) => flow.actuator).filter((code): code is string => code !== null))]

function source(state: { reported: boolean | null; connectivity?: string; enabled?: boolean }): ScenarioSource {
  const connectivity = state.connectivity ?? "ONLINE"
  return {
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: null, template_code: null, enabled: state.enabled ?? true, connectivity, last_seen_at: null }],
      sensors: [],
      actuators: WIRED.map((code) => ({ id: `a-${code}`, code, name: code, actuator_model_code: code, device_id: "dev-1", enabled: true })),
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity, last_seen_at: null }],
      sensors: [],
      actuators: WIRED.map((code) => ({ id: `a-${code}`, desired_state: true, reported_state: state.reported, synchronization: "IN_SYNC", command_status: null, command_time: null, last_ack_at: null, failure_reason: null })),
      alerts: [],
    },
    updated_at: "2026-09-30T02:00:00Z",
  } as unknown as ScenarioSource
}

const bound: ScadaFlow = { id: "f", name: "Mạch thử", actuator: "FISH_TANK_PUMP", tone: "sky", d: "M 0 0 L 10 10" }

describe("isFlowing", () => {
  it("runs a flow that is not wired to any device yet, so the drawing can be checked", () => {
    expect(isFlowing(source({ reported: null }), { ...bound, actuator: null })).toBe(true)
  })

  it("runs only while the device reports itself on", () => {
    expect(isFlowing(source({ reported: true }), bound)).toBe(true)
    expect(isFlowing(source({ reported: false }), bound)).toBe(false)
  })

  it("stands still when the device is unreachable, rather than claiming water is moving", () => {
    expect(isFlowing(source({ reported: true, connectivity: "OFFLINE" }), bound)).toBe(false)
    expect(isFlowing(source({ reported: true, enabled: false }), bound)).toBe(false)
  })
})

describe("SCADA_FLOWS wiring", () => {
  it("names only actuators the diagram actually knows about", () => {
    // Gõ sai mã cơ cấu thì mạch im lặng không chảy mãi mãi mà chẳng báo lỗi ở đâu.
    const known = new Set(SCADA_METRICS.filter((m) => m.kind === "ACTUATOR").map((m) => m.code))
    for (const flow of SCADA_FLOWS) {
      if (flow.actuator !== null) expect(known.has(flow.actuator)).toBe(true)
    }
  })

  it("leaves unwired only the branches whose valve has no device record yet", () => {
    // Danh sách này là lời nhắc: mạch nằm đây chảy bất kể ngoài vườn ra sao.
    // Thêm được cơ cấu cho cái van tương ứng thì phải bỏ nó khỏi đây.
    expect(SCADA_FLOWS.filter((flow) => flow.actuator === null).map((flow) => flow.id)).toEqual([
      "flow-12",
      "flow-13",
      "flow-16",
      "flow-17",
    ])
  })
})

describe("ScadaFlowLayer", () => {
  const markup = renderToStaticMarkup(<ScadaFlowLayer source={source({ reported: true })} />)

  it("draws every pipe on the artwork coordinate grid", () => {
    expect(markup).toContain('viewBox="0 0 1750 1100"')
    for (const flow of SCADA_FLOWS) expect(markup).toContain(flow.d)
  })

  it("sends small arrows along each pipe to show the water moving", () => {
    expect(markup).toContain("scada-flow-arrow-run")
    expect(markup).toContain("offset-path")
  })

  it("keeps a stopped pipe on the diagram, only still and dimmed", () => {
    const stopped = renderToStaticMarkup(<ScadaFlowLayer source={source({ reported: false })} />)
    // Đường ống vẫn vẽ đủ, chỉ mờ đi và bỏ lớp hoạt hình
    for (const flow of SCADA_FLOWS) expect(stopped).toContain(flow.d)
    const wired = SCADA_FLOWS.filter((flow) => flow.actuator !== null).length
    expect(stopped.match(/opacity="0.45"/g)?.length).toBe(wired)
  })

  it("draws the arrows as outlines, so the pipe colour still shows through them", () => {
    expect(markup).toContain("stroke-white")
    // Đặc ruột sẽ bịt kín một mảng trắng trong lòng ống
    expect(markup).not.toContain("fill-white")
  })

  it("spaces the arrows evenly, so a long pipe gets more of them than a short one", () => {
    const longest = [...SCADA_FLOWS].sort((a, b) => polylineLength(b.d) - polylineLength(a.d))[0]
    const shortest = [...SCADA_FLOWS].sort((a, b) => polylineLength(a.d) - polylineLength(b.d))[0]
    expect(arrowCount(longest.d)).toBeGreaterThan(arrowCount(shortest.d))
    expect(arrowCount(shortest.d)).toBeGreaterThanOrEqual(1)
  })

  it("leaves the arrows parked at even intervals when motion is turned off", () => {
    // Hoạt hình tắt thì offset-distance tĩnh phải khác nhau, nếu không mũi tên
    // dồn hết về đầu đường và chiều nước biến mất.
    expect(markup).toContain("offset-distance:0%")
    expect(markup).toContain("offset-distance:50%")
  })

  it("lays a light casing under each line so it never blends into the blue pipes", () => {
    expect(markup).toContain("stroke-white")
    expect(markup).toContain("stroke-sky-400")
  })

  it("caps every pipe with an arrow, so where the water ends is never guesswork", () => {
    expect(markup).toContain("scada-flow-end")
    expect(markup.match(/marker-end/g)?.length).toBe(SCADA_FLOWS.length)
  })

  it("stays out of the way of clicks and of screen readers", () => {
    // Lớp này chỉ tô đậm đường ống đã vẽ; số liệu thật nằm ở thẻ bên trên.
    expect(markup).toContain("pointer-events-none")
    expect(markup).toContain('aria-hidden="true"')
  })
})
