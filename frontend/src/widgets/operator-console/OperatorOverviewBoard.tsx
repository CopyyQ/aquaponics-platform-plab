import type { LucideIcon } from "lucide-react"
import { AlertTriangle, Cloud, Droplets, Gauge, Lightbulb, Thermometer, Waves } from "lucide-react"
import { Link } from "react-router-dom"
import type { OperatorActuatorChip, OperatorOverviewModel, OperatorSensorCard, OperatorSensorIcon, OperatorValueStatus } from "./operator-console.model"
import { formatCompactNumber } from "./operator-console.model"
import { formatVietnamTime } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Card } from "@/shared/ui/card"
import { Skeleton } from "@/shared/ui/skeleton"
import { EmptyState } from "@/shared/ui/empty-state"

const iconMap: Record<OperatorSensorIcon, LucideIcon> = {
  ph: Droplets,
  humidity: Cloud,
  waterTemp: Thermometer,
  airTemp: Thermometer,
  level: Waves,
  light: Lightbulb,
  tds: Gauge,
  pressure: Gauge,
  generic: Droplets,
}

const statusLabel: Record<OperatorValueStatus, string> = {
  NORMAL: "Bình thường",
  ATTENTION: "Cần xem",
  NO_DATA: "Chưa có dữ liệu",
}

export function OperatorSensorCardView({ sensor }: { sensor: OperatorSensorCard }) {
  const Icon = iconMap[sensor.icon]
  const attention = sensor.status === "ATTENTION"
  const missing = sensor.status === "NO_DATA"
  const valueText = missing || sensor.value === null ? "—" : formatCompactNumber(sensor.value)
  const footnote = attention ? sensor.rangeLabel : sensor.recordedAt ? `Cập nhật ${formatVietnamTime(sensor.recordedAt)}` : "Chưa có dữ liệu"
  return (
    <Card className="rounded-2xl border-0 p-4 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
      <div className="flex items-start justify-between gap-3">
        <div className={cn("grid size-10 place-items-center rounded-full", attention ? "bg-amber-100 text-amber-600" : "bg-emerald-50 text-emerald-600")}>
          <Icon className="size-5" aria-hidden="true" />
        </div>
        <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", attention ? "bg-amber-50 text-amber-700" : missing ? "bg-slate-100 text-slate-500" : "bg-emerald-50 text-emerald-700")}>
          {statusLabel[sensor.status]}
        </span>
      </div>
      <p className={cn("mt-4 text-3xl font-semibold tracking-tight", attention ? "text-amber-500" : "text-slate-900")}>
        {valueText}
        {missing || sensor.value === null ? null : <span className="ml-1 text-lg font-medium text-slate-400">{sensor.unit}</span>}
      </p>
      <p className="mt-2 text-sm font-medium text-slate-700">{sensor.name}</p>
      <p className="mt-1 text-xs text-slate-400">{footnote ?? "Chưa có ngưỡng an toàn"}</p>
    </Card>
  )
}

function ActuatorChip({ actuator }: { actuator: OperatorActuatorChip }) {
  const on = actuator.on === true
  const unknown = actuator.on === null
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-sm">
      <span className="font-medium text-slate-700">{actuator.name}</span>
      <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", on ? "text-emerald-600" : "text-slate-400")}>
        <span className={cn("size-2 rounded-full", on ? "bg-emerald-500" : "bg-slate-300")} />
        {unknown ? "CHƯA RÕ" : on ? "BẬT" : "TẮT"}
      </span>
    </div>
  )
}

export function OperatorOverviewBoard({ model, systemId }: { model: OperatorOverviewModel; systemId: string }) {
  return (
    <div className="space-y-5">
      {model.banner ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800">
          <p className="inline-flex items-center gap-2 text-sm font-medium">
            <AlertTriangle className="size-4" aria-hidden="true" />
            {model.banner}
          </p>
          <Link className="text-sm font-semibold text-amber-700 hover:underline" to={`/aquaponics-systems/${systemId}/alerts`}>Xem ngay →</Link>
        </div>
      ) : null}

      {model.sensors.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {model.sensors.map((sensor) => <OperatorSensorCardView key={sensor.id} sensor={sensor} />)}
        </div>
      ) : (
        <EmptyState icon={Droplets} title="Chưa có cảm biến" description="Hệ thống này chưa có cảm biến runtime để hiển thị giá trị mới nhất." />
      )}

      <Card className="rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-800">Thiết bị</h2>
          <Link className="text-sm font-medium text-emerald-700 hover:underline" to={`/aquaponics-systems/${systemId}/devices`}>Quản lý →</Link>
        </div>
        {model.actuators.length ? (
          <div className="flex flex-wrap gap-2">
            {model.actuators.map((actuator) => <ActuatorChip key={actuator.id} actuator={actuator} />)}
          </div>
        ) : (
          <p className="text-sm text-slate-500">Chưa có cơ cấu chấp hành.</p>
        )}
      </Card>
    </div>
  )
}

export function OperatorOverviewSkeleton() {
  return <div className="space-y-4"><Skeleton className="h-14" /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div><Skeleton className="h-28" /></div>
}
