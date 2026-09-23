import { Link } from "react-router-dom"
import { Activity, Cpu, ListChecks, Radio, TriangleAlert, Waypoints } from "lucide-react"
import type { Alert, AquaponicsSystem, Device, MonitoringLatest } from "@/api/contracts"
import { Card } from "@/shared/ui/card"
import { StatusBadge } from "@/shared/ui/status-badge"
import { formatRelative } from "@/shared/lib/date"

interface BreakdownTile {
  label: string
  count: number
  tone: "muted" | "success" | "info" | "warning" | "danger"
  color: string
}

interface DiagramDeviceRow {
  id: string
  name: string
  code: string
  status: string
  sensorCount: number
  actuatorCount: number
  location: string | null
}

export interface AquaponicsSystemOverviewViewModel {
  system: AquaponicsSystem
  deviceCount: number
  onlineDevices: number
  sensorCount: number
  reportingSensors: number
  actuatorCount: number
  activeAlerts: number
  actuatorsNeedingAttention: number
  lastUpdatedAt: string | null
  diagramDevices: DiagramDeviceRow[]
  sensorBreakdown: BreakdownTile[]
  actuatorBreakdown: BreakdownTile[]
}

export function createOverviewViewModel(system: AquaponicsSystem, devices: Device[], latest: MonitoringLatest | undefined, alerts: Alert[]): AquaponicsSystemOverviewViewModel {
  const latestDevices = latest?.devices ?? []
  const onlineDevices = latestDevices.filter((device) => device.connection_status === "ONLINE").length
  const sensorCount = devices.reduce((total, device) => total + device.sensors.length, 0)
  const actuatorCount = devices.reduce((total, device) => total + device.actuators.length, 0)
  const reportingSensors = latestDevices.reduce((total, device) => total + device.sensors.filter((sensor) => sensor.latest?.value !== null && sensor.latest?.value !== undefined).length, 0)

  const sensors = latestDevices.flatMap((device) => device.sensors)
  const actuators = latestDevices.flatMap((device) => device.actuators)

  const outOfRangeSensors = sensors.filter((sensor) => sensor.threshold_state === "ABOVE" || sensor.threshold_state === "BELOW").length
  const noDataSensors = Math.max(sensorCount - reportingSensors, 0)
  const inRangeSensors = Math.max(reportingSensors - outOfRangeSensors, 0)

  const outOfSyncActuators = actuators.filter((actuator) => actuator.synchronization_status === "OUT_OF_SYNC").length
  const syncedActuators = Math.max(actuatorCount - outOfSyncActuators, 0)
  const timedOutActuators = actuators.filter((actuator) => actuator.latest_command?.status === "TIMEOUT" || actuator.latest_command?.status === "FAILED").length
  const actuatorsNeedingAttention = actuators.filter((actuator) => actuator.synchronization_status === "OUT_OF_SYNC" || actuator.latest_command?.status === "TIMEOUT" || actuator.latest_command?.status === "FAILED").length

  const activeAlertsCount = alerts.filter((alert) => alert.status !== "RESOLVED").length

  const timestamps = sensors.map((sensor) => sensor.latest?.recorded_at).filter((value): value is string => Boolean(value))
  const lastUpdatedAt = timestamps.length ? timestamps.reduce((latestValue, current) => (current > latestValue ? current : latestValue)) : null

  const latestById = new Map(latestDevices.map((device) => [String(device.id), device]))
  const diagramDevices: DiagramDeviceRow[] = devices.map((device) => ({
    id: String(device.id), name: device.name, code: device.code,
    status: latestById.get(String(device.id))?.connection_status ?? device.status,
    sensorCount: device.sensors.length, actuatorCount: device.actuators.length, location: device.location,
  }))

  const sensorBreakdown: BreakdownTile[] = [
    { label: "Trong ngưỡng", count: inRangeSensors, tone: "success", color: "#10b981" },
    { label: "Vượt ngưỡng", count: outOfRangeSensors, tone: "danger", color: "#ef4444" },
    { label: "Chưa có dữ liệu", count: noDataSensors, tone: "muted", color: "#cbd5e1" },
  ]
  const actuatorBreakdown: BreakdownTile[] = [
    { label: "Đã đồng bộ", count: syncedActuators, tone: "success", color: "#10b981" },
    { label: "Chưa đồng bộ", count: outOfSyncActuators, tone: "warning", color: "#fbbf24" },
    { label: "Lệnh hết thời gian chờ", count: timedOutActuators, tone: "danger", color: "#ef4444" },
  ]

  return {
    system, deviceCount: devices.length, onlineDevices, sensorCount, reportingSensors, actuatorCount,
    activeAlerts: activeAlertsCount, actuatorsNeedingAttention, lastUpdatedAt,
    diagramDevices, sensorBreakdown, actuatorBreakdown,
  }
}

const toneClass: Record<BreakdownTile["tone"], string> = {
  muted: "bg-muted/60 text-muted-foreground",
  success: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  info: "bg-sky-500/10 text-sky-700 dark:text-sky-400",
  warning: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  danger: "bg-red-500/10 text-red-700 dark:text-red-400",
}

function SegmentedRing({ tiles, size = 56, strokeWidth = 7 }: { tiles: BreakdownTile[]; size?: number; strokeWidth?: number }) {
  const radius = (size - strokeWidth) / 2
  const center = size / 2
  const circumference = 2 * Math.PI * radius
  const total = tiles.reduce((sum, tile) => sum + tile.count, 0)
  let cumulative = 0
  return <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
    <circle cx={center} cy={center} r={radius} fill="none" stroke="currentColor" strokeWidth={strokeWidth} className="text-muted" />
    {total > 0 && tiles.map((tile) => {
      if (tile.count <= 0) return null
      const length = circumference * (tile.count / total)
      const dashoffset = -cumulative
      cumulative += length
      return <circle key={tile.label} cx={center} cy={center} r={radius} fill="none" stroke={tile.color} strokeWidth={strokeWidth} strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={dashoffset} transform={`rotate(-90 ${center} ${center})`} />
    })}
  </svg>
}

function BreakdownGroup({ title, total, tiles }: { title: string; total: number; tiles: BreakdownTile[] }) {
  return <div className="flex items-center gap-4">
    <div className="relative shrink-0">
      <SegmentedRing tiles={tiles} />
      <div className="absolute inset-0 flex items-center justify-center text-sm font-bold">{total}</div>
    </div>
    <div>
      <p className="text-xs font-semibold text-muted-foreground">{title} ({total})</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {tiles.map((tile) => <div key={tile.label} className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium ${toneClass[tile.tone]}`}>
          <span className="text-sm font-bold">{tile.count}</span>
          <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: tile.color }} />
          {tile.label}
        </div>)}
      </div>
    </div>
  </div>
}

export function OverviewDashboard({ model }: { model: AquaponicsSystemOverviewViewModel }) {
  const coveragePercent = model.sensorCount ? Math.round((model.reportingSensors / model.sensorCount) * 100) : 0
  const offlineOrMissingSensors = Math.max(model.sensorCount - model.reportingSensors, 0)

  const cards = [
    { label: "Thiết bị", value: model.deviceCount, detail: `${model.onlineDevices} đang trực tuyến`, icon: Cpu },
    { label: "Cảm biến", value: model.sensorCount, detail: `${model.reportingSensors} đang có dữ liệu`, icon: Activity },
    { label: "Cơ cấu chấp hành", value: model.actuatorCount, detail: model.actuatorsNeedingAttention ? `${model.actuatorsNeedingAttention} cần chú ý` : "Đang hoạt động bình thường", icon: Radio },
    { label: "Cảnh báo đang mở", value: model.activeAlerts, detail: "xem chi tiết bên dưới", icon: TriangleAlert },
  ]

  return <div className="space-y-6">

    {/* KPI row */}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, detail, icon: Icon }) => <Card key={label}><div className="flex items-start justify-between p-4"><div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></div><div className="rounded-xl bg-primary/10 p-2.5 text-primary"><Icon className="size-5" aria-hidden="true" /></div></div></Card>)}</div>

    {/* Sơ đồ vận hành | Độ phủ dữ liệu cảm biến */}
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <div className="flex items-center justify-between gap-3 p-5 pb-3.5">
          <div className="flex items-center gap-2"><Waypoints className="size-5 text-primary" aria-hidden="true" /><span className="font-semibold">Danh sách thiết bị vận hành</span></div>
          <Link to="../scada" className="text-sm font-medium text-primary hover:underline whitespace-nowrap">Xem chi tiết →</Link>
        </div>
        <div className="flex flex-col gap-2.5 px-5 pb-5">
          {model.diagramDevices.length ? model.diagramDevices.map((device) => <Link key={device.id} to={`../devices/${device.id}`} className="rounded-lg border p-3.5 transition-colors hover:border-primary">
            <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-sm font-semibold">{device.name}</p><p className="text-xs text-muted-foreground">{device.code}</p></div><StatusBadge value={device.status} /></div>
            <div className="mt-3 grid grid-cols-2 gap-2.5 text-sm">
              <div className="rounded-lg bg-muted/60 p-2.5"><p className="text-xs text-muted-foreground">Cảm biến</p><p className="mt-0.5 text-base font-semibold">{device.sensorCount}</p></div>
              <div className="rounded-lg bg-muted/60 p-2.5"><p className="text-xs text-muted-foreground">Cơ cấu chấp hành</p><p className="mt-0.5 text-base font-semibold">{device.actuatorCount}</p></div>
            </div>
            <p className="mt-2.5 text-xs text-muted-foreground">{device.location ?? "Chưa đặt vị trí"}</p>
          </Link>) : <p className="text-sm text-muted-foreground">Chưa có thiết bị.</p>}
        </div>
      </Card>

      <Card>
        <div className="p-5 pb-1 font-semibold">Độ phủ dữ liệu cảm biến</div>
        <div className="px-5 pb-5 pt-3">
          <p className="text-2xl font-bold">{model.reportingSensors}/{model.sensorCount}</p>
          <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${coveragePercent}%` }} /></div>
          <p className="mt-2 text-xs text-muted-foreground">{offlineOrMissingSensors} ngoại tuyến/mất dữ liệu · cập nhật {formatRelative(model.lastUpdatedAt)}</p>
        </div>
      </Card>
    </div>

    {/* Tình trạng thiết bị */}
    <Card>
      <div className="flex items-center justify-between gap-3 p-5 pb-3.5">
        <div className="flex items-center gap-2"><ListChecks className="size-5 text-primary" aria-hidden="true" /><span className="font-semibold">Tình trạng thiết bị</span></div>
        <Link to="../devices" className="text-sm font-medium text-primary hover:underline whitespace-nowrap">Xem chi tiết tình trạng thiết bị →</Link>
      </div>
      <div className="grid gap-6 px-5 pb-5 sm:grid-cols-2 sm:divide-x sm:divide-border">
        <div className="sm:pr-8"><BreakdownGroup title="Cảm biến" total={model.sensorCount} tiles={model.sensorBreakdown} /></div>
        <div className="sm:pl-8"><BreakdownGroup title="Cơ cấu chấp hành" total={model.actuatorCount} tiles={model.actuatorBreakdown} /></div>
      </div>
    </Card>

  </div>
}
