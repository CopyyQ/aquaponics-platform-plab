import { SCADA_AERATOR } from "@/entities/scada/model/scada-cards"
import { readActuator } from "@/entities/scada/model/scada-signals"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"

/** Khung toạ độ của tranh gốc, dùng chung với lớp dòng nước. */
const ART_WIDTH = 1750
const ART_HEIGHT = 1100

/**
 * Chùm bọt khí, mô tả bằng số cố định thay vì sinh ngẫu nhiên.
 *
 * `x` là vị trí ngang trong khung (0 sát trái, 1 sát phải), `r` là bán kính theo đơn vị
 * tranh, `dur` và `delay` tính bằng giây. Chọn lệch nhau để chùm bọt không nhấp nháy
 * đồng loạt như một khối; ngẫu nhiên thật sẽ khiến mỗi lần vẽ lại một khác.
 */
const BUBBLES = [
  { x: 0.5, r: 3.4, dur: 1.7, delay: 0 },
  { x: 0.38, r: 2.5, dur: 2.1, delay: 0.3 },
  { x: 0.62, r: 2.9, dur: 1.9, delay: 0.6 },
  { x: 0.45, r: 4.2, dur: 2.3, delay: 0.9 },
  { x: 0.7, r: 2.2, dur: 1.6, delay: 1.2 },
  { x: 0.28, r: 3.5, dur: 2.4, delay: 1.5 },
  { x: 0.56, r: 2.7, dur: 1.8, delay: 1.8 },
  { x: 0.34, r: 3.1, dur: 2.0, delay: 0.15 },
  { x: 0.76, r: 2.6, dur: 2.2, delay: 0.75 },
  { x: 0.22, r: 2.4, dur: 1.7, delay: 1.05 },
  { x: 0.66, r: 3.3, dur: 2.5, delay: 2.0 },
] as const

/** Máy sủi có đang thổi khí hay không, theo đúng trạng thái thiết bị báo về. */
export function isAerating(source: ScenarioSource) {
  const signal = readActuator(source, SCADA_AERATOR.code)
  return signal.status === "AVAILABLE" && signal.value === true
}

/**
 * Bọt khí máy sủi, vẽ đè lên vùng nước trong bể cá.
 *
 * Máy tắt thì không vẽ gì: bể cá trong tranh đã có sẵn hình bọt, nên thêm bọt tĩnh
 * chỉ làm rối mà không nói thêm điều gì. Có bọt nổi lên nghĩa là máy đang chạy thật.
 */
export function ScadaAerator({ source }: { source: ScenarioSource }) {
  if (!isAerating(source)) return null

  const { x, y, w, h } = SCADA_AERATOR.box
  const left = (x / 100) * ART_WIDTH
  const width = (w / 100) * ART_WIDTH
  const bottom = ((y + h) / 100) * ART_HEIGHT
  const rise = (h / 100) * ART_HEIGHT

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${ART_WIDTH} ${ART_HEIGHT}`}
      aria-hidden="true"
    >
      {BUBBLES.map((bubble, index) => (
        <circle
          key={index}
          cx={left + bubble.x * width}
          cy={bottom}
          r={bubble.r}
          className="scada-bubble fill-white"
          style={{
            "--scada-bubble-rise": `${-rise}px`,
            "--scada-bubble-duration": `${bubble.dur}s`,
            animationDelay: `-${bubble.delay}s`,
          } as React.CSSProperties}
        />
      ))}
    </svg>
  )
}
