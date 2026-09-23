import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BellRing } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import type {
  ProjectScenarioBranch,
  ProjectScenarioBranchCreate,
  ProjectScenarioItem,
} from "@/api/contracts"
import { errorMessage } from "@/api/client"
import {
  createProjectScenarioBranch,
  deleteProjectScenarioBranch,
  getProjectScenario,
  queryKeys,
  updateProjectScenarioBranch,
} from "@/api/resources"
import { useAuth } from "@/app/auth"
import { ProjectScenarioBranchDialog } from "@/features/manage-project-scenarios/components/ProjectScenarioBranchDialog"
import { ProjectScenarioResourceGroup } from "@/features/manage-project-scenarios/components/ProjectScenarioResourceGroup"
import { Card, CardContent } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"

interface EditingBranch {
  item: ProjectScenarioItem
  branch: ProjectScenarioBranch | null
}

export function ProjectScenarioDetailPage() {
  const params = useParams()
  const systemId = params.systemId ?? ""
  const deviceId = params.deviceId ?? ""
  const scenarioId = params.scenarioId ?? ""
  const valid = Boolean(systemId && deviceId && scenarioId)
  const { can } = useAuth()
  const client = useQueryClient()
  const [editing, setEditing] = useState<EditingBranch | null>(null)

  const scenario = useQuery({
    queryKey: queryKeys.projectScenario(systemId, deviceId, scenarioId),
    queryFn: () => getProjectScenario(systemId, deviceId, scenarioId),
    enabled: valid,
  })

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({
        queryKey: queryKeys.projectScenario(systemId, deviceId, scenarioId),
      }),
      client.invalidateQueries({
        queryKey: queryKeys.projectScenarios(systemId, deviceId),
      }),
    ])
  }

  const saveBranch = useMutation({
    mutationFn: async (payload: ProjectScenarioBranchCreate) => {
      if (!editing) throw new Error("Chưa chọn resource")
      if (editing.branch) {
        return updateProjectScenarioBranch(
          systemId,
          deviceId,
          scenarioId,
          editing.item.id,
          editing.branch.id,
          payload,
        )
      }
      return createProjectScenarioBranch(
        systemId,
        deviceId,
        scenarioId,
        editing.item.id,
        payload,
      )
    },
    onSuccess: async () => {
      await refresh()
      setEditing(null)
    },
  })

  const removeBranch = useMutation({
    mutationFn: ({
      item,
      branch,
    }: {
      item: ProjectScenarioItem
      branch: ProjectScenarioBranch
    }) =>
      deleteProjectScenarioBranch(
        systemId,
        deviceId,
        scenarioId,
        item.id,
        branch.id,
      ),
    onSuccess: refresh,
  })

  if (!valid) {
    return (
      <EmptyState
        icon={BellRing}
        title="Đường dẫn kịch bản không hợp lệ"
        description="System, Device và Scenario ID phải đầy đủ."
      />
    )
  }
  if (scenario.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-72" />
      </div>
    )
  }
  if (scenario.isError || !scenario.data) {
    return (
      <EmptyState
        icon={BellRing}
        title="Không thể tải kịch bản"
        description={errorMessage(scenario.error)}
      />
    )
  }

  const value = scenario.data
  const canWrite = can("project_scenarios.update")

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">
          <Link
            className="text-primary hover:underline"
            to={`/aquaponics-systems/${systemId}/devices/${deviceId}`}
          >
            Thiết bị
          </Link>{" "}
          / Kịch bản
        </p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-semibold">{value.name}</h2>
              {value.is_active ? (
                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                  ĐANG SỬ DỤNG
                </span>
              ) : (
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                  Chưa sử dụng
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {value.description || "Không có mô tả"}
            </p>
          </div>
        </div>
      </div>

      <Card>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Cảm biến</p>
            <p className="mt-1 font-semibold">{value.sensor_count}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Cơ cấu chấp hành</p>
            <p className="mt-1 font-semibold">{value.actuator_count}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Nguồn khởi tạo</p>
            <p className="mt-1 font-semibold">
              {value.source_scenario_catalog_id != null
                ? `Catalog #${value.source_scenario_catalog_id}`
                : "Kịch bản độc lập"}
            </p>
          </div>
        </CardContent>
      </Card>

      <ProjectScenarioResourceGroup
        title="Cảm biến"
        items={value.sensors}
        canWrite={canWrite}
        onAdd={(item) => setEditing({ item, branch: null })}
        onEdit={(item, branch) => setEditing({ item, branch })}
        onDelete={(item, branch) => removeBranch.mutate({ item, branch })}
      />

      <ProjectScenarioResourceGroup
        title="Cơ cấu chấp hành"
        items={value.actuators}
        canWrite={canWrite}
        onAdd={(item) => setEditing({ item, branch: null })}
        onEdit={(item, branch) => setEditing({ item, branch })}
        onDelete={(item, branch) => removeBranch.mutate({ item, branch })}
      />

      {removeBranch.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(removeBranch.error)}
        </p>
      ) : null}

      <ProjectScenarioBranchDialog
        targetType={editing?.item.target_type ?? "SENSOR"}
        branch={editing?.branch ?? null}
        open={editing != null}
        pending={saveBranch.isPending}
        error={saveBranch.error}
        onOpenChange={(open) => {
          if (!open) setEditing(null)
        }}
        onSubmit={(payload) => saveBranch.mutate(payload)}
      />
    </div>
  )
}
