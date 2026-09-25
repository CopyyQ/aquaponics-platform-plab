import type { ScadaRuntimeResponse } from "@/api/contracts"
import {
  deriveScadaScenarioSignals,
  resolveScadaScenarioImage,
  type ScenarioSignal,
  type ScenarioSignalStatus,
} from "@/entities/scada/model/scenario-image"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"

type ScenarioRuntime = Pick<ScadaRuntimeResponse, "aquaponics_system" | "inventory" | "runtime" | "updated_at">

const statusLabels: Record<ScenarioSignalStatus, string> = {
  AVAILABLE: "Có dữ liệu",
  NONE: "Chưa có dữ liệu",
  STALE: "Dữ liệu cũ",
  INVALID: "Dữ liệu không hợp lệ",
  OFFLINE: "Thiết bị ngoại tuyến",
  DISABLED: "Đã vô hiệu hóa",
}

function signalText<T>(signal: ScenarioSignal<T>, available: (value: T) => string) {
  return signal.value !== null && signal.status === "AVAILABLE" ? available(signal.value) : statusLabels[signal.status]
}
const fallbackLabels = {
  FEEDER: "máy cho cá ăn",
  WEATHER: "thời tiết",
  LIGHT: "trạng thái đèn",
} as const

export function ScadaScenarioImage({ runtime, localHour }: { runtime: ScenarioRuntime; localHour?: number }) {
  const hour = localHour ?? new Date(runtime.updated_at).getHours()
  const signals = deriveScadaScenarioSignals(runtime, hour)
  const selection = resolveScadaScenarioImage(signals)

  const rows = [
    { label: "Mực nước bể cá", source: signals.waterLevel.sourceCode ?? "NONE", value: signalText(signals.waterLevel, (value) => `${value}%`) },
    { label: "Đèn chiếu sáng", source: signals.growLightOn.sourceCode ?? "NONE", value: signalText(signals.growLightOn, (value) => value ? "Bật" : "Tắt") },
    { label: "Máy cho cá ăn", source: signals.feederOpen.sourceCode ?? "NONE", value: signalText(signals.feederOpen, (value) => value ? "Mở nắp" : "Đóng nắp") },
    { label: "Thời tiết", source: signals.raining.sourceCode ?? "NONE", value: signalText(signals.raining, (value) => value ? "Mưa" : "Không mưa") },
  ]

  return <div className="space-y-4">
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">SCADA theo dữ liệu Project</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {selection.assetUrl && selection.filename ? <div className="overflow-hidden rounded-xl border bg-muted/20">
          <img
            src={selection.assetUrl}
            alt={`Sơ đồ Aquaponics theo dữ liệu Project: ${selection.filename}`}
            className="block h-auto w-full object-contain"
          />
        </div> : <div className="flex min-h-64 items-center justify-center rounded-xl border border-dashed bg-muted/20 p-8 text-center text-sm text-muted-foreground">
          Chưa đủ dữ liệu WATER_LEVELW2 (mực nước bể cá) hợp lệ để chọn ảnh SCADA.
        </div>}

        {selection.fallbackDimensions.length ? <div className="rounded-lg border border-amber-300/60 bg-amber-50 p-3 text-sm text-amber-900">
          Một số phần của ảnh chỉ là biến thể minh họa vì database chưa có dữ liệu: {selection.fallbackDimensions.map((item) => fallbackLabels[item]).join(", ")}. Các trạng thái này vẫn được giữ là NONE và không được coi là trạng thái vận hành thật.
        </div> : null}

        {selection.tankVisualLevel !== null ? <p className="text-xs text-muted-foreground">
          Ảnh mực nước sử dụng bucket gần nhất: {selection.tankVisualLevel}%. Giá trị thực vẫn hiển thị bên dưới.
        </p> : null}
      </CardContent>
    </Card>
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-base">Ánh xạ dữ liệu runtime</CardTitle></CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {rows.map((row) => <div key={row.label} className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">{row.label}</p>
          <p className="mt-1 font-semibold">{row.value}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">Nguồn: {row.source}</p>
        </div>)}
      </CardContent>
    </Card>
  </div>
}
