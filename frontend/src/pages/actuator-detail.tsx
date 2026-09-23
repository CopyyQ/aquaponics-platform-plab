import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, CirclePower, Clock3, Gauge } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import {
  createCommand,
  getActuator,
  listActuatorCommands,
  listActuatorReadings,
  listProjectScenarios,
  queryKeys,
} from "@/api/resources"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"

export function ActuatorDetailPage() {
  const params = useParams()
  const systemId = params.systemId ?? ""
  const deviceId = params.deviceId ?? ""
  const actuatorId = params.actuatorId ?? ""
  const { can } = useAuth()
  const client = useQueryClient()
  const [pending, setPending] = useState<boolean | null>(null)
  const valid = Boolean(systemId && deviceId && actuatorId)

  const actuator = useQuery({
    queryKey: queryKeys.actuator(systemId, deviceId, actuatorId),
    queryFn: () => getActuator(systemId, deviceId, actuatorId),
    enabled: valid,
  })
  const readings = useQuery({
    queryKey: queryKeys.actuatorReadings(systemId, deviceId, actuatorId, 50),
    queryFn: () => listActuatorReadings(systemId, deviceId, actuatorId, 50),
    enabled: valid && can("actuators.readings.read"),
  })
  const commands = useQuery({
    queryKey: queryKeys.actuatorCommands(systemId, deviceId, actuatorId, 20),
    queryFn: () => listActuatorCommands(systemId, deviceId, actuatorId, 20),
    enabled: valid && can("actuators.commands.read"),
  })
  const projectScenarios = useQuery({
    queryKey: queryKeys.projectScenarios(systemId, deviceId),
    queryFn: () => listProjectScenarios(systemId, deviceId),
    enabled: valid,
  })

  const command = useMutation({
    mutationFn: (desired_state: boolean) =>
      createCommand(systemId, deviceId, actuatorId, { desired_state }),
    onSuccess: async () => {
      setPending(null)
      await Promise.all([
        client.invalidateQueries({
          queryKey: queryKeys.device(systemId, deviceId),
        }),
        client.invalidateQueries({
          queryKey: queryKeys.actuator(systemId, deviceId, actuatorId),
        }),
        client.invalidateQueries({
          queryKey: queryKeys.actuatorCommands(
            systemId,
            deviceId,
            actuatorId,
            20,
          ),
        }),
      ])
    },
  })

  if (actuator.isLoading) return <Skeleton className="h-96" />
  if (actuator.isError || !actuator.data) {
    return (
      <EmptyState
        icon={CirclePower}
        title="Không thể tải Actuator"
        description={errorMessage(actuator.error)}
      />
    )
  }

  const value = actuator.data
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
          / Actuator
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h2 className="text-2xl font-semibold">{value.name}</h2>
          <StatusBadge
            value={
              value.reported_state === true
                ? "ONLINE"
                : value.reported_state === false
                  ? "OFFLINE"
                  : "WAITING_CONNECTION"
            }
          />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {value.code} · {value.location ?? "Chưa đặt vị trí"}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Info
          label="Model"
          value={value.actuator_model_id ? String(value.actuator_model_id) : "—"}
        />
        <Info label="Desired" value={stateText(pending ?? value.desired_state)} />
        <Info label="Reported" value={stateText(value.reported_state)} />
        <Info
          label="Điện áp / dòng"
          value={`${value.voltage_v ?? "—"} V · ${value.current_a ?? "—"} A`}
        />
      </div>

      {can("actuators.commands.create") ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CirclePower className="size-5 text-primary" />
              Điều khiển vận hành
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => {
                setPending(true)
                command.mutate(true)
              }}
              disabled={command.isPending}
            >
              <CheckCircle2 />
              Bật
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setPending(false)
                command.mutate(false)
              }}
              disabled={command.isPending}
            >
              Tắt
            </Button>
            <span className="text-sm text-muted-foreground">
              Lệnh được gửi qua MQTT và chỉ xác nhận trạng thái sau khi thiết bị
              phản hồi.
            </span>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-2">
        <HistoryCard title="Lịch sử lệnh" icon={Clock3}>
          {commands.data?.length ? (
            commands.data.map((item) => (
              <div
                key={item.command_id}
                className="flex items-center justify-between border-b py-3 last:border-0"
              >
                <span>
                  {item.desired_state ? "Bật" : "Tắt"} · {item.status}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(item.requested_at).toLocaleString("vi-VN")}
                </span>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              Chưa có lịch sử command.
            </p>
          )}
        </HistoryCard>
        <HistoryCard title="Điện áp / dòng điện" icon={Gauge}>
          {readings.data?.length ? (
            readings.data.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between border-b py-3 last:border-0"
              >
                <span>
                  {item.voltage_v ?? "—"} V · {item.current_a ?? "—"} A
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(item.recorded_at).toLocaleString("vi-VN")}
                </span>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              Chưa có reading.
            </p>
          )}
        </HistoryCard>
      </div>

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

function stateText(value: boolean | null) {
  return value === null ? "—" : value ? "Bật" : "Tắt"
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

function HistoryCard({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: typeof Clock3
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="size-5 text-primary" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}
