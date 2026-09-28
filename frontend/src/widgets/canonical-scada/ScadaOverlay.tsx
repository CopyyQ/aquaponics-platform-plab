import { AlertTriangle, Droplets, Fish, Waves } from "lucide-react"
import { Link } from "react-router-dom"
import type { ScadaIssue, ScadaRuntimeResponse } from "@/api/contracts"
import { TANK_FULL_THRESHOLD, deriveScadaScenarioSignals, resolveScadaScenarioImage } from "@/entities/scada/model/scenario-image"
import { SCADA_CARDS, SCADA_LEVEL_GAUGE, SCADA_SYSTEM_CARD } from "@/entities/scada/model/scada-cards"
import type { ScadaCard, ScadaCardIcon } from "@/entities/scada/model/scada-cards"
import { readScadaMetrics, statusText } from "@/entities/scada/model/scada-readings"
import type { ScadaReading } from "@/entities/scada/model/scada-readings"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { resolveCardStatus, resolveSystemStatus } from "@/entities/scada/model/scada-status"
import type { ScadaCardStatus, ScadaHealth } from "@/entities/scada/model/scada-status"
import { formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/shared/ui/dialog"

type OverlaySource = ScenarioSource & Pick<ScadaRuntimeResponse, "aquaponics_system" | "issues">

/** Số chỉ số hiện trên mặt thẻ; phần còn lại xem trong hộp chi tiết. */
const FACE_LIMIT = 2

// Bám đúng bảng màu của chức năng Cảnh báo: hồng đỏ = nghiêm trọng, hổ phách = chưa xử lý,
// xanh lá = ổn. Không dùng màu cam để hai nơi không nói hai thứ tiếng khác nhau.
const DOT: Record<ScadaHealth, string> = {
  OK: "bg-emerald-500",
  CAUTION: "bg-amber-500",
  WARNING: "bg-amber-500",
  CRITICAL: "bg-rose-500",
  UNKNOWN: "bg-slate-400",
}

/** Quầng sáng quanh chấm trạng thái, giúp nó nổi trên nền tranh nhiều màu. */
const HALO: Record<ScadaHealth, string> = {
  OK: "ring-emerald-500/25",
  CAUTION: "ring-amber-500/25",
  WARNING: "ring-amber-500/25",
  CRITICAL: "ring-rose-500/25",
  UNKNOWN: "ring-slate-400/25",
}

const BADGE: Record<ScadaHealth, string> = {
  OK: "bg-emerald-50 text-emerald-700",
  CAUTION: "bg-amber-100 text-amber-700",
  WARNING: "bg-amber-100 text-amber-700",
  CRITICAL: "bg-rose-100 text-rose-700",
  UNKNOWN: "bg-slate-100 text-slate-600",
}

/** Khối sự cố tô theo mức độ của chính nó, không phải mức nặng nhất của cả thẻ. */
function issueTone(severity: ScadaIssue["severity"]) {
  if (severity === "CRITICAL" || severity === "HIGH") {
    return { box: "border-rose-200 bg-rose-50", title: "text-rose-800", body: "text-rose-700" }
  }
  if (severity === "WARNING") {
    return { box: "border-amber-200 bg-amber-50", title: "text-amber-800", body: "text-amber-700" }
  }
  return { box: "border-slate-200 bg-slate-50", title: "text-slate-800", body: "text-slate-600" }
}

/**
 * Thẻ đồng hồ nằm trên màn hình tối của tủ điện nên phải dùng chữ sáng;
 * các thẻ khác nằm trên vùng sáng của tranh nên dùng chữ tối.
 */
function valueTone(reading: ScadaReading, onDarkScreen = false) {
  if (reading.status !== "AVAILABLE") {
    return onDarkScreen ? "text-slate-300 font-medium italic" : "text-slate-400 font-medium italic"
  }
  if (reading.unvalidated) return onDarkScreen ? "text-amber-300" : "text-amber-700"
  return onDarkScreen ? "text-white" : "text-slate-900"
}

function readingText(reading: ScadaReading) {
  return reading.text ?? statusText(reading.status)
}

function StatusDot({ health, className }: { health: ScadaHealth; className?: string }) {
  return (
    <span
      className={cn("inline-block shrink-0 rounded-full ring-2", DOT[health], HALO[health], className)}
      aria-hidden="true"
    />
  )
}

const ICONS: Record<ScadaCardIcon, typeof Droplets> = {
  droplets: Droplets,
  waves: Waves,
  fish: Fish,
}

/** Huy hiệu chỉ mang màu nhận diện, không kiêm nhiệm việc báo trạng thái. */
function IconBadge({ icon }: { icon?: ScadaCardIcon }) {
  if (!icon) return null
  const Glyph = ICONS[icon]
  return (
    <span className="grid size-[1.55em] shrink-0 place-items-center rounded-full bg-sky-500 text-white" aria-hidden="true">
      <Glyph className="size-[0.9em]" strokeWidth={2.6} />
    </span>
  )
}

/** Hàng tiêu đề chung cho thẻ chỉ số và thẻ tình trạng hệ thống. */
function CardHeading({ health, icon, children }: { health: ScadaHealth; icon?: ScadaCardIcon; children: string }) {
  return (
    // Tiêu đề được phép xuống dòng: chiều cao thẻ tự giãn, cắt cụt tên sẽ mất nghĩa.
    // Chấm trạng thái đứng riêng sau tên thẻ, không dính vào biểu tượng,
    // để biểu tượng chỉ nói "thẻ này về cái gì" còn chấm chỉ nói "đang ra sao".
    <p className="mb-[0.45em] flex items-center gap-[0.5em] text-[0.92em] leading-tight font-bold tracking-tight text-slate-800">
      <IconBadge icon={icon} />
      {/* Tên thẻ luôn nằm một hàng; khung thẻ phải đủ rộng cho tên dài nhất. */}
      <span className="whitespace-nowrap">{children}</span>
      <StatusDot health={health} className="size-[0.42em]" />
    </p>
  )
}

function CardFace({ card, readings, status }: { card: ScadaCard; readings: ScadaReading[]; status: ScadaCardStatus }) {
  const shown = card.valueOnly ? readings : readings.slice(0, FACE_LIMIT)
  const hidden = readings.length - shown.length

  return (
    <>
      {card.title ? (
        <CardHeading health={status.health} icon={card.icon}>{card.title}</CardHeading>
      ) : (
        // Thẻ đồng hồ không có tiêu đề để gắn đèn, nên đặt chấm trạng thái ở góc.
        <StatusDot health={status.health} className="absolute top-[0.35em] right-[0.35em] size-[0.36em]" />
      )}

      {readings.length === 0 ? (
        <p className={cn("text-center text-[1em] font-bold", card.valueOnly ? "text-slate-400" : "text-slate-300")}>—</p>
      ) : null}

      {shown.map((reading) => (
        <p
          key={reading.code}
          className={cn(
            "flex gap-[0.6em] py-[0.12em]",
            card.stacked ? "flex-col gap-0" : "items-baseline",
            card.valueOnly ? "justify-center" : "justify-between",
          )}
        >
          {card.valueOnly ? null : (
            <span
              className={cn(
                "text-[0.76em] font-medium text-slate-500",
                // Thẻ xếp dọc có trọn một dòng cho nhãn nên không cần cắt cụt
                card.stacked ? "leading-snug" : "truncate",
              )}
            >
              {reading.label}
            </span>
          )}
          <span
            className={cn(
              "tabular-nums whitespace-nowrap",
              card.valueOnly ? "text-[1.02em] font-extrabold tracking-tight" : "text-[0.86em] font-bold",
              valueTone(reading, card.valueOnly),
            )}
          >
            {readingText(reading)}
          </span>
        </p>
      ))}

      {hidden > 0 ? (
        <p className="mt-[0.3em] text-[0.66em] font-medium text-slate-400">+{hidden} chỉ số</p>
      ) : null}
    </>
  )
}

function CardDetail({ card, readings, status }: { card: ScadaCard; readings: ScadaReading[]; status: ScadaCardStatus }) {
  return (
    <DialogContent
      // Nền chỉ tối đi, không làm mờ: sơ đồ phía sau vẫn phải đọc được khi đối chiếu.
      overlayClassName="bg-slate-900/35 backdrop-blur-none duration-200 data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0"
      className={cn(
        "max-w-lg duration-200 ease-out",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:slide-in-from-bottom-2",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
      )}
    >
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2.5 text-slate-900">
          <StatusDot health={status.health} className="size-2.5" />
          {card.title ?? "Chi tiết chỉ số"}
        </DialogTitle>
        <DialogDescription asChild>
          <div className="flex items-center gap-2">
            <span>Tình trạng</span>
            <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", BADGE[status.health])}>
              {status.label}
            </span>
          </div>
        </DialogDescription>
      </DialogHeader>

      <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200">
        {readings.map((reading) => (
          <li key={reading.code} className="flex items-start justify-between gap-4 px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-700">{reading.fullLabel}</p>
              {reading.recordedAt ? (
                <p className="mt-0.5 text-xs text-slate-400">Ghi nhận {formatRelative(reading.recordedAt)}</p>
              ) : null}
              {reading.unvalidated ? (
                <p className="mt-0.5 text-xs text-amber-700">Chưa khai báo miền hợp lệ nên giá trị chưa được đối chiếu.</p>
              ) : null}
            </div>
            <span className={cn("shrink-0 text-sm font-bold tabular-nums", valueTone(reading))}>
              {readingText(reading)}
            </span>
          </li>
        ))}
      </ul>

      {status.issues.length ? (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-slate-700">Sự cố đang ghi nhận</h4>
          {status.issues.map((issue) => {
            const tone = issueTone(issue.severity)
            return (
              <div key={issue.id} className={cn("flex gap-2.5 rounded-xl border p-3", tone.box)}>
                <AlertTriangle className={cn("mt-0.5 size-4 shrink-0", tone.title)} aria-hidden="true" />
                <div className="min-w-0">
                  <p className={cn("text-sm font-semibold", tone.title)}>{issue.title}</p>
                  <p className={cn("mt-0.5 text-xs", tone.body)}>{issue.root_cause}</p>
                  {issue.suggested_action ? (
                    <p className={cn("mt-1 text-xs", tone.body)}>Nên làm: {issue.suggested_action}</p>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      ) : null}
    </DialogContent>
  )
}

// Bóng và viền dùng px: Tailwind không sinh CSS cho shadow/ring khai báo bằng em.
// Không nền, không bóng, không viền: chữ và biểu tượng nổi thẳng trên tranh.
const SHELL = "absolute rounded-[0.6em] px-[0.35em] py-[0.25em] text-[1.4cqw] leading-tight"

function OverlayCard({ card, source }: { card: ScadaCard; source: OverlaySource }) {
  const readings = readScadaMetrics(source, card.items)
  const status = resolveCardStatus(readings, source.issues)

  const style = {
    left: `${card.box.x}%`,
    width: `${card.box.w}%`,
    minHeight: `${card.box.h}%`,
    ...(card.anchor === "bottom"
      ? { bottom: `${100 - (card.box.y + card.box.h)}%` }
      : { top: `${card.box.y}%` }),
  }

  // Thẻ rỗng không có gì để xem thêm nên không mở hộp chi tiết.
  if (!readings.length) {
    return (
      <div className={cn(SHELL, "flex flex-col justify-center")} style={style}>
        <CardFace card={card} readings={readings} status={status} />
      </div>
    )
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={`${card.title ?? "Chỉ số"} — ${status.label}. Bấm để xem chi tiết.`}
          className={cn(
            SHELL,
            "cursor-pointer text-left transition duration-150",
            // Nền chỉ hiện khi rê chuột, để người dùng biết thẻ bấm được
            "hover:bg-white/70",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600",
          )}
          style={style}
        >
          <CardFace card={card} readings={readings} status={status} />
        </button>
      </DialogTrigger>
      <CardDetail card={card} readings={readings} status={status} />
    </Dialog>
  )
}

/**
 * Thẻ tình trạng hệ thống: nói bằng câu người dùng hiểu ngay thay vì liệt kê chỉ số,
 * và khi có vấn đề thì dẫn thẳng sang trang cảnh báo để xử lý.
 */
function SystemCard({ source, readings }: { source: OverlaySource; readings: ScadaReading[] }) {
  const status = resolveSystemStatus(readings, source.issues)
  const healthy = status.health === "OK"
  const box = SCADA_SYSTEM_CARD.box

  return (
    // Riêng thẻ này có khung trắng: nó là kết luận chung của cả hệ thống nên cần
    // tách khỏi tranh, khác với các thẻ chỉ số vốn để chữ nổi thẳng trên nền.
    <div
      className={cn(
        SHELL,
        // w-max: khung ôm sát dòng chữ dài nhất thay vì cố định bề ngang,
        // max-w phòng trường hợp câu trạng thái dài bất thường.
        "flex w-max max-w-[38%] flex-col rounded-[0.8em] bg-white/95 px-[0.85em] py-[0.7em]",
        "shadow-[0_4px_16px_-4px_rgba(15,23,42,0.22),0_1px_3px_rgba(15,23,42,0.08)]",
      )}
      style={{ left: `${box.x}%`, top: `${box.y}%` }}
    >
      <CardHeading health={status.health}>Tình trạng hệ thống</CardHeading>

      <p
        className={cn(
          "text-[0.82em] leading-snug font-semibold",
          healthy ? "text-emerald-700" : "text-rose-700",
        )}
      >
        {healthy ? "Hệ thống hoạt động bình thường" : "Hệ thống có vấn đề"}
      </p>

      {healthy ? null : (
        <Link
          to={`/aquaponics-systems/${source.aquaponics_system.id}/alerts`}
          className="mt-[0.5em] self-start rounded-full bg-rose-600 px-[0.85em] py-[0.3em] text-[0.74em] font-bold text-white transition hover:bg-rose-700"
        >
          Kiểm tra ngay →
        </Link>
      )}
    </div>
  )
}

/**
 * Cột đo mực nước bể cá: ảnh nền chỉ vẽ được hai mức 60% và 100%, nên đây là
 * chỗ duy nhất trên sơ đồ thể hiện mực nước liên tục đúng theo số đo.
 *
 * Ống lấy đúng toạ độ đã hiệu chỉnh nên cao bằng bể và sát cạnh phải; nhãn và
 * vạch chia nằm ngoài ống nên không đè lên hình.
 */
function LevelGauge({ source }: { source: OverlaySource }) {
  const [reading] = readScadaMetrics(source, [SCADA_LEVEL_GAUGE.code])
  const box = SCADA_LEVEL_GAUGE.box
  const percent = reading.value === null ? null : Math.min(100, Math.max(0, reading.value))
  const isFull = percent !== null && percent >= TANK_FULL_THRESHOLD

  return (
    <div
      className="absolute text-[1.4cqw] leading-none"
      style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.w}%`, height: `${box.h}%` }}
      role="img"
      aria-label={`Mực nước bể cá: ${reading.text ?? statusText(reading.status)}`}
    >
      <span className="absolute -top-[1.7em] left-1/2 -translate-x-1/2 text-[0.8em] font-bold whitespace-nowrap text-slate-700">
        Mực nước
      </span>

      <div className="absolute inset-0 overflow-hidden rounded-full border-[0.12em] border-sky-300 bg-white/80">
        {percent === null ? null : (
          <div className="absolute inset-x-0 bottom-0 bg-sky-500" style={{ height: `${percent}%` }}>
            {/* Gợn sóng mặt nước; tràn lên trên bị ống cắt gọn */}
            <svg
              viewBox="0 0 20 4"
              preserveAspectRatio="none"
              className="absolute -top-[0.26em] left-0 h-[0.3em] w-full"
              aria-hidden="true"
            >
              <path d="M0 3 Q 5 0 10 3 T 20 3 V4 H0 Z" fill="#0ea5e9" />
            </svg>
          </div>
        )}
      </div>

      {/* Vạch chia dài bằng cột. Vạch ngang và chữ bám đúng mặt nước, nên nó vừa
          báo trạng thái vừa chỉ đúng chỗ — không còn cảnh chữ nằm một nơi, nước một nẻo. */}
      <div className="absolute top-0 left-full ml-[0.5em] h-full">
        <span className="absolute top-0 left-0 h-full w-[0.09em] bg-sky-300" aria-hidden="true" />

        {percent === null ? null : (
          <div className="absolute left-0 w-full" style={{ top: `${100 - percent}%` }}>
            <span
              className={cn("absolute -left-[0.28em] h-[0.09em] w-[0.65em]", isFull ? "bg-sky-400" : "bg-slate-400")}
              aria-hidden="true"
            />
            <p
              className={cn(
                "absolute left-[0.6em] -translate-y-[0.5em] text-[0.82em] font-bold whitespace-nowrap",
                isFull ? "text-sky-700" : "text-slate-600",
              )}
            >
              {isFull ? "Full" : "Thiếu"}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function ReadingList({ readings, title }: { readings: ScadaReading[]; title: string }) {
  if (!readings.length) return null
  return (
    <section className="mt-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">{title}</h3>
      <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200">
        {readings.map((reading) => (
          <li key={reading.code} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
            <span className="min-w-0 truncate text-sm text-slate-600">{reading.fullLabel}</span>
            <span className={cn("shrink-0 text-sm font-bold tabular-nums", valueTone(reading))}>
              {readingText(reading)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * Sơ đồ SCADA: ảnh nền chọn theo dữ liệu, phủ các thẻ chỉ số lên đúng vị trí đã hiệu chỉnh.
 * Mặt thẻ chỉ nêu chỉ số chính kèm đèn trạng thái; bấm vào mở hộp chi tiết đầy đủ.
 *
 * Bề rộng bị chặn bởi chiều cao khả dụng (chiều cao x 1.5) nên toàn bộ sơ đồ luôn nằm gọn
 * trong một màn hình, không phải cuộn. Chữ dùng đơn vị cqw nên co giãn cùng khung.
 * Dưới 1024px lớp phủ tắt và chỉ số rơi xuống danh sách, vì chữ khi đó quá nhỏ để đọc.
 */
export function ScadaOverlay({ runtime, localHour }: { runtime: OverlaySource; localHour?: number }) {
  const hour = localHour ?? new Date(runtime.updated_at).getHours()
  const selection = resolveScadaScenarioImage(deriveScadaScenarioSignals(runtime, hour))
  const onImage = readScadaMetrics(runtime, SCADA_CARDS.flatMap((card) => card.items))

  return (
    <div>
      {/* Chiều rộng bị chặn bởi chiều cao khả dụng nên sơ đồ luôn gọn trong một màn hình.
          Dùng style nội tuyến vì Tailwind không sinh được giá trị tuỳ ý có dấu phẩy lồng trong min(). */}
      <div
        className="@container relative mx-auto aspect-3/2 overflow-hidden rounded-2xl bg-slate-100 ring-1 ring-slate-900/5"
        style={{ width: "min(100%, calc((100dvh - 7.5rem) * 1.5))" }}
      >
        {selection.assetUrl && selection.label ? (
          <img
            src={selection.assetUrl}
            alt={`Sơ đồ Aquaponics: ${selection.label}`}
            className="absolute inset-0 h-full w-full object-contain"
          />
        ) : (
          <p className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-slate-500">
            Chưa đủ dữ liệu mực nước bể cá hợp lệ để chọn ảnh sơ đồ.
          </p>
        )}

        {selection.assetUrl ? (
          <div className="hidden lg:block" data-testid="scada-overlay">
            <LevelGauge source={runtime} />
            <SystemCard source={runtime} readings={onImage} />
            {SCADA_CARDS.map((card) => <OverlayCard key={card.id} card={card} source={runtime} />)}
          </div>
        ) : null}
      </div>

      <div className="lg:hidden">
        <ReadingList readings={onImage} title="Thông số trên sơ đồ" />
      </div>
    </div>
  )
}
