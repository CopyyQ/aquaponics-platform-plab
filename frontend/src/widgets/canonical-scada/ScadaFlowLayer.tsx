import { SCADA_FLOWS, polylineLength, type ScadaFlow } from "@/entities/scada/model/scada-flows"
import { readActuator } from "@/entities/scada/model/scada-signals"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { cn } from "@/shared/lib/utils"

/** Khung toạ độ của tranh gốc; đường đi trong scada-flows.ts tính theo hệ này. */
const ART_WIDTH = 1750
const ART_HEIGHT = 1100

/** Khoảng cách mong muốn giữa hai mũi tên, tính theo đơn vị của tranh. */
const ARROW_SPACING = 115
/** Một vòng chạy hết đường; phải khớp với thời lượng khai trong index.css. */
const CYCLE_SECONDS = 4

/**
 * Mũi tên nhỏ trôi trong ống: đầu nhọn kèm một đoạn đuôi phía sau.
 * Vẽ quanh gốc toạ độ, mũi hướng theo trục X để motion path xoay cho đúng chiều ống.
 */
const ARROW_SHAPE = "M 4.8 0 L 0 -2.7 L 0 -1.3 L -5.6 -1.3 L -5.6 1.3 L 0 1.3 L 0 2.7 Z"

const END_MARKER_ID = "scada-flow-end"

/**
 * Mạch chỉ chảy khi biết chắc thiết bị đang chạy.
 *
 * Mất kết nối hay dữ liệu cũ thì đứng yên: hoạt hình là lời khẳng định "nước đang
 * chảy ngay lúc này", mà lúc đó ta không biết điều đó. Thà không nói còn hơn nói sai.
 */
export function isFlowing(source: ScenarioSource, flow: ScadaFlow) {
  if (flow.actuator === null) return true
  const signal = readActuator(source, flow.actuator)
  return signal.status === "AVAILABLE" && signal.value === true
}

/** Số mũi tên rải trên một mạch, luôn ít nhất một cái kể cả đoạn ống rất ngắn. */
export function arrowCount(d: string) {
  return Math.max(1, Math.round(polylineLength(d) / ARROW_SPACING))
}

function FlowArrows({ flow, running }: { flow: ScadaFlow; running: boolean }) {
  const count = arrowCount(flow.d)
  return (
    <>
      {Array.from({ length: count }, (_, index) => {
        // Vị trí xuất phát rải đều, kèm độ trễ âm tương ứng để lúc chạy chúng vẫn
        // cách đều nhau. Tắt hoạt hình thì mỗi mũi tên nằm lại đúng chỗ này.
        const start = (index / count) * 100
        const offset = flow.reverse ? 100 - start : start
        return (
          <path
            key={index}
            d={ARROW_SHAPE}
            // Viền trắng, ruột rỗng: nét mảnh cho cảm giác đồ hoạ infographic sắc gọn,
            // và để lộ màu ống phía sau thay vì bịt kín một mảng trắng.
            className={cn("scada-flow-arrow stroke-white", running && "scada-flow-arrow-run")}
            fill="none"
            strokeWidth={1}
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{
              offsetPath: `path("${flow.d}")`,
              offsetDistance: `${offset}%`,
              animationDelay: `-${(start / 100) * CYCLE_SECONDS}s`,
              animationDirection: flow.reverse ? "reverse" : undefined,
            }}
          />
        )
      })}
    </>
  )
}

/**
 * Lớp nước chảy nằm giữa ảnh nền và các thẻ chỉ số.
 *
 * Mỗi mạch gồm ba lớp chồng nhau: viền trắng lót dưới tách khỏi tranh, thân ống xanh
 * liền mạch, rồi những mũi tên trắng nhỏ trôi bên trong. Tranh nền vốn đã toàn ống
 * xanh nên thiếu lớp lót là đường nước lẫn vào hình.
 *
 * Đây là lớp trang trí làm rõ thêm đường ống đã vẽ trong tranh, mọi thông tin đều có
 * ở thẻ bên trên, nên ẩn hẳn khỏi trình đọc màn hình thay vì đọc ra "flow-1, flow-2".
 */
export function ScadaFlowLayer({ source }: { source: ScenarioSource }) {
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${ART_WIDTH} ${ART_HEIGHT}`}
      fill="none"
      aria-hidden="true"
    >
      <defs>
        {/* Cuối ống: một mũi tên viền lớn rồi một mũi nhỏ hơn nối sau, cho biết nước
            đi tới đâu là hết. Cả hai nằm lùi vào trong ống nên không tràn ra tranh.
            Nằm ngoài luồng hoạt hình nên vẫn thấy khi người dùng tắt chuyển động. */}
        {/* markerUnits userSpaceOnUse: kích thước tính thẳng bằng đơn vị tranh, không
            nhân theo bề dày nét — nhờ vậy mũi tên luôn nhỏ hơn lòng ống dù ống đổi dày mỏng. */}
        <marker
          id={END_MARKER_ID}
          viewBox="0 0 16 10"
          refX="14"
          refY="5"
          markerWidth="16"
          markerHeight="10"
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <g className="stroke-white" fill="none" strokeLinecap="round" strokeLinejoin="round">
            <path d="M 2 2.2 L 7.5 5 L 2 7.8" strokeWidth={1.5} />
            <path d="M 10.5 3.4 L 14 5 L 10.5 6.6" strokeWidth={1.2} />
          </g>
        </marker>
      </defs>

      {SCADA_FLOWS.map((flow) => {
        const running = isFlowing(source, flow)
        return (
        // Thiết bị tắt thì đường ống vẫn vẽ đủ, chỉ mờ đi và mũi tên đứng lại.
        // Xoá hẳn đường sẽ khiến sơ đồ trông như thiếu mất một nhánh dẫn nước.
        <g key={flow.id} opacity={running ? 1 : 0.45}>
          {/* Quầng sáng mảnh vừa đủ tách đường nước khỏi ống xanh vẽ trong tranh.
              Giữ hẹp hơn ống trên tranh để lớp này nằm gọn bên trong, không tràn ra hình. */}
          <path
            d={flow.d}
            className="stroke-white"
            strokeWidth={13}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.5}
          />
          <path
            d={flow.d}
            className="stroke-sky-400"
            strokeWidth={11}
            strokeLinecap="round"
            strokeLinejoin="round"
            markerEnd={flow.reverse ? undefined : `url(#${END_MARKER_ID})`}
            markerStart={flow.reverse ? `url(#${END_MARKER_ID})` : undefined}
          />
          <FlowArrows flow={flow} running={running} />
        </g>
        )
      })}
    </svg>
  )
}
