import { useQuery } from "@tanstack/react-query"
import { Activity } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import {
  getSensor,
  getSensorTelemetry,
  listProjectScenarios,
  queryKeys,
} from "@/api/resources"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { MonitoringChart } from "@/widgets/canonical-monitoring/MonitoringChart"
import { Card, CardContent } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"

export function SensorDetailPage() {
  const params = useParams()
  const systemId = params.systemId ?? ""
  const deviceId = params.deviceId ?? ""
  const sensorId = params.sensorId ?? ""
  const { can } = useAuth()
  const valid = Boolean(systemId && deviceId && sensorId)

  const sensor = useQuery({
    queryKey: queryKeys.sensor(systemId, deviceId, sensorId),
    queryFn: () => getSensor(systemId, deviceId, sensorId),
    enabled: valid,
  })
  const telemetry = useQuery({
    queryKey: queryKeys.sensorTelemetry(
      systemId,
      deviceId,
      sensorId,
      undefined,
      undefined,
      200,
    ),
    queryFn: () =>
      getSensorTelemetry(systemId, deviceId, sensorId, { limit: 200 }),
    enabled: valid && can("sensors.telemetry.read"),
  })
  const projectScenarios = useQuery({
    queryKey: queryKeys.projectScenarios(systemId, deviceId),
    queryFn: () => listProjectScenarios(systemId, deviceId),
    enabled: valid,
  })

  if (sensor.isLoading) return <Skeleton className="h-96" />
  if (sensor.isError || !sensor.data) {
    return (
      <EmptyState
        icon={Activity}
        title="Không thể tải Sensor"
        description={errorMessage(sensor.error)}
      />
    )
  }

  const value = sensor.data
  const chart = telemetry.data
    ? {
        sensor_id: value.id,
        unit: "",
        points: telemetry.data.map((item) => ({
          recorded_at: item.recorded_at,
          value: item.value,
        })),
        gaps: [],
      }
    : null
  const activeScenario =
    projectScenarios.data?.find((scenario) => scenario.is_active) ?? null

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">
          <Link
            className="text-primary hover:underline"
            to={`/aquaponics-systems/${systemId}/devices/${deviceId}`}
          >
            Device
          </Link>{" "}
          / Sensor
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h2 className="text-2xl font-semibold">{value.name}</h2>
          <StatusBadge value={value.status} />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {value.code} · {value.description ?? "Không có mô tả"}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Info label="Sensor ID" value={String(value.id)} />
        <Info label="SensorModel" value={String(value.sensor_model_id)} />
        <Info
          label="Vị trí"
          value={value.installation_location ?? "Chưa đặt vị trí"}
        />
      </div>

      {chart ? (
        <MonitoringChart series={chart} />
      ) : (
        <EmptyState
          icon={Activity}
          title="Chưa có telemetry"
          description="Không có dữ liệu trong khoảng truy vấn hiện tại."
        />
      )}

      {projectScenarios.isLoading ? (
        <Skeleton className="h-28" />
      ) : (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">
              Kịch bản đang sử dụng
            </p>
            {activeScenario ? (
              <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
                <p className="font-semibold">{activeScenario.name}</p>
                <Link
                  className="text-sm text-primary hover:underline"
                  to={`/aquaponics-systems/${systemId}/devices/${deviceId}/scenarios/${activeScenario.id}`}
                >
                  Mở cấu hình trong kịch bản
                </Link>
              </div>
            ) : (
              <p className="mt-1 text-sm">
                Chưa có kịch bản active cho Device này.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 font-semibold">{value}</p>
      </CardContent>
    </Card>
  )
}
