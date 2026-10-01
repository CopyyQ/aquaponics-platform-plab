import type { CSSProperties } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { createCommand, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { cn } from "@/shared/lib/utils"
import { COMMAND_BLOCK_REASON } from "../model/scada-actuator-target"
import type { ScadaActuatorTarget } from "../model/scada-actuator-target"

// Kích thước công tắc (px). Núm trượt hết rãnh: TRAVEL = rãnh − núm − 2 lần khe hở.
const TRACK_W = 74
const TRACK_H = 32
const KNOB = 26
const GAP = 3
const TRAVEL = TRACK_W - KNOB - GAP * 2

// Hình học và màu đặt bằng style nội tuyến chứ không qua lớp Tailwind tuỳ ý:
// công tắc phải luôn hiện đủ rãnh và núm, không phụ thuộc vào việc lớp CSS có được sinh ra hay không.
const TRACK_TONE: Record<"on" | "off" | "unknown", CSSProperties> = {
  on: {
    background: "linear-gradient(180deg, #34d399 0%, #10b981 100%)",
    color: "#ffffff",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.35), 0 4px 12px -4px rgba(16,185,129,0.65)",
  },
  off: {
    background: "linear-gradient(180deg, #e2e8f0 0%, #cbd5e1 100%)",
    color: "#475569",
    boxShadow: "inset 0 1px 3px rgba(15,23,42,0.18)",
  },
  unknown: {
    background: "#f1f5f9",
    color: "#94a3b8",
    boxShadow: "inset 0 0 0 1px #cbd5e1",
  },
}

/**
 * Công tắc bật/tắt cơ cấu trong hộp chi tiết: núm trắng trượt trong rãnh,
 * chữ BẬT/TẮT nằm ở phần rãnh còn trống phía đối diện núm.
 *
 * Không dùng Switch của shadcn vì nó không chứa được chữ bên trong.
 */
export function ScadaActuatorToggle({
  systemId,
  target,
  className,
}: {
  systemId: string
  target: ScadaActuatorTarget
  className?: string
}) {
  const client = useQueryClient()
  const command = useMutation({
    mutationFn: (next: boolean) =>
      createCommand(systemId, target.deviceId, target.actuatorId, { desired_state: next }),
    onSuccess: async (_created, next) => {
      await client.invalidateQueries({ queryKey: queryKeys.monitoringLatest(systemId) })
      toast.success(`Đã gửi lệnh ${next ? "bật" : "tắt"} ${target.name}`, {
        description: "Đang chờ thiết bị xác nhận.",
      })
    },
    onError: (error) =>
      toast.error(`Không gửi được lệnh cho ${target.name}`, { description: errorMessage(error) }),
  })

  const on = target.on === true
  const unknown = target.on === null
  const busy = command.isPending || target.pending
  const blocked = target.availability.allowed ? null : COMMAND_BLOCK_REASON[target.availability.reason]
  const disabled = busy || blocked !== null
  // Chưa rõ trạng thái thì bấm là bật: an toàn hơn đoán là đang bật rồi tắt đi.
  const next = !on
  const label = unknown ? "—" : on ? "BẬT" : "TẮT"
  const hint = busy ? "Đang chờ thiết bị xác nhận" : (blocked ?? `Bấm để ${next ? "bật" : "tắt"}`)

  return (
    <button
      type="button"
      role="switch"
      aria-checked={unknown ? "mixed" : on}
      aria-label={`${target.name}: ${unknown ? "chưa rõ trạng thái" : on ? "đang bật" : "đang tắt"}. ${hint}.`}
      title={hint}
      disabled={disabled}
      onClick={() => command.mutate(next)}
      className={cn(
        "relative shrink-0 rounded-full select-none",
        "transition-[transform,filter] duration-200 ease-out",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600",
        disabled ? "cursor-not-allowed" : "cursor-pointer hover:brightness-105 active:scale-95",
        className,
      )}
      style={{
        width: TRACK_W,
        height: TRACK_H,
        transition: "background 300ms ease, box-shadow 300ms ease, transform 200ms ease, filter 200ms ease",
        opacity: blocked && !busy ? 0.55 : 1,
        ...TRACK_TONE[unknown ? "unknown" : on ? "on" : "off"],
      }}
    >
      {/* Chữ nằm ở nửa rãnh không bị núm che: bật thì chữ bên trái, tắt thì bên phải. */}
      <span
        className="absolute inset-y-0 flex items-center justify-center font-extrabold leading-none tracking-wide"
        style={{
          fontSize: 12,
          left: on ? GAP + 6 : GAP + KNOB,
          right: on ? GAP + KNOB : GAP + 6,
          transition: "left 300ms ease, right 300ms ease",
        }}
      >
        {label}
      </span>

      <span
        aria-hidden="true"
        className="absolute grid place-items-center rounded-full"
        style={{
          top: GAP,
          left: GAP,
          width: KNOB,
          height: KNOB,
          background: "#ffffff",
          boxShadow: "0 1px 2px rgba(15,23,42,0.25), 0 2px 6px rgba(15,23,42,0.18)",
          transform: `translateX(${on ? TRAVEL : 0}px)`,
          transition: "transform 300ms cubic-bezier(0.34, 1.4, 0.64, 1)",
        }}
      >
        {busy ? (
          <Loader2 className="animate-spin" size={14} strokeWidth={3} color={on ? "#059669" : "#64748b"} />
        ) : null}
      </span>
    </button>
  )
}
