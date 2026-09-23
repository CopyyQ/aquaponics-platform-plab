import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Pencil, Play, Plus, Trash2 } from "lucide-react"
import { Link } from "react-router-dom"

import type { ProjectScenarioSummary } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import {
  deleteProjectScenario,
  listProjectScenarios,
  queryKeys,
  updateProjectScenario,
} from "@/api/resources"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
import { EmptyState } from "@/shared/ui/empty-state"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Skeleton } from "@/shared/ui/skeleton"
import { Textarea } from "@/shared/ui/textarea"

import { ActivateProjectScenarioDialog } from "./ActivateProjectScenarioDialog"
import { CreateProjectScenarioDialog } from "./CreateProjectScenarioDialog"

export function ProjectScenarioCard({
  scenario,
  systemId,
  deviceId,
  canCreate,
  canUpdate,
  canDelete,
  canActivate,
  onClone,
  onEdit,
  onDelete,
  onActivate,
}: {
  scenario: ProjectScenarioSummary
  systemId: string
  deviceId: string
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  canActivate: boolean
  onClone: (scenario: ProjectScenarioSummary) => void
  onEdit: (scenario: ProjectScenarioSummary) => void
  onDelete: (scenario: ProjectScenarioSummary) => void
  onActivate: (scenario: ProjectScenarioSummary) => void
}) {
  return (
    <Card className={scenario.is_active ? "border-primary/60" : undefined}>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="break-words text-base">{scenario.name}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {scenario.description || "Không có mô tả"}
            </p>
          </div>
          {scenario.is_active ? (
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
              ĐANG SỬ DỤNG
            </span>
          ) : (
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              Chưa sử dụng
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
          <span>{scenario.sensor_count} cảm biến</span>
          <span>{scenario.actuator_count} cơ cấu chấp hành</span>
          {scenario.source_scenario_catalog_id != null ? (
            <span>Mẫu Catalog #{scenario.source_scenario_catalog_id}</span>
          ) : (
            <span>Kịch bản độc lập</span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <Link
              to={`/aquaponics-systems/${systemId}/devices/${deviceId}/scenarios/${scenario.id}`}
            >
              Mở
            </Link>
          </Button>

          {canCreate ? (
            <Button size="sm" variant="outline" onClick={() => onClone(scenario)}>
              <Copy />
              Nhân bản
            </Button>
          ) : null}

          {canUpdate ? (
            <Button size="sm" variant="outline" onClick={() => onEdit(scenario)}>
              <Pencil />
              Sửa
            </Button>
          ) : null}

          {!scenario.is_active && canActivate ? (
            <Button size="sm" onClick={() => onActivate(scenario)}>
              <Play />
              Sử dụng
            </Button>
          ) : null}

          {!scenario.is_active && canDelete ? (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onDelete(scenario)}
            >
              <Trash2 />
              Xóa
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

export function ProjectScenarioList({
  systemId,
  deviceId,
  canCreate,
  canUpdate,
  canDelete,
  canActivate,
}: {
  systemId: string
  deviceId: string
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  canActivate: boolean
}) {
  const client = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [cloneSource, setCloneSource] = useState<ProjectScenarioSummary | null>(null)
  const [activateTarget, setActivateTarget] = useState<ProjectScenarioSummary | null>(null)
  const [editTarget, setEditTarget] = useState<ProjectScenarioSummary | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProjectScenarioSummary | null>(null)
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")

  const scenarios = useQuery({
    queryKey: queryKeys.projectScenarios(systemId, deviceId),
    queryFn: () => listProjectScenarios(systemId, deviceId),
    enabled: Boolean(systemId && deviceId),
  })

  const activeScenario =
    scenarios.data?.find((scenario) => scenario.is_active) ?? null

  const refresh = async () => {
    await client.invalidateQueries({
      queryKey: queryKeys.projectScenarios(systemId, deviceId),
    })
  }

  const editMutation = useMutation({
    mutationFn: async () => {
      if (!editTarget) throw new Error("Chưa chọn kịch bản")
      return updateProjectScenario(systemId, deviceId, editTarget.id, {
        name: editName.trim(),
        description: editDescription.trim() || null,
      })
    },
    onSuccess: async () => {
      await refresh()
      setEditTarget(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!deleteTarget) throw new Error("Chưa chọn kịch bản")
      await deleteProjectScenario(systemId, deviceId, deleteTarget.id)
    },
    onSuccess: async () => {
      await refresh()
      setDeleteTarget(null)
    },
  })

  const openEdit = (scenario: ProjectScenarioSummary) => {
    setEditTarget(scenario)
    setEditName(scenario.name)
    setEditDescription(scenario.description ?? "")
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Kịch bản của thiết bị</CardTitle>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Mỗi kịch bản chứa toàn bộ cảm biến và cơ cấu chấp hành của Device.
            Chỉ kịch bản đang sử dụng mới được phép tạo cảnh báo và Telegram.
          </p>
          {activeScenario ? (
            <p className="mt-2 text-sm">
              Kịch bản đang dùng:{" "}
              <span className="font-medium">{activeScenario.name}</span>
            </p>
          ) : null}
        </div>
        {canCreate ? (
          <Button
            onClick={() => {
              setCloneSource(null)
              setCreateOpen(true)
            }}
          >
            <Plus />
            Tạo kịch bản
          </Button>
        ) : null}
      </CardHeader>

      <CardContent>
        {scenarios.isLoading ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </div>
        ) : scenarios.isError ? (
          <EmptyState
            icon={Play}
            title="Không thể tải kịch bản"
            description={errorMessage(scenarios.error)}
          />
        ) : scenarios.data?.length ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {scenarios.data.map((scenario) => (
              <ProjectScenarioCard
                key={scenario.id}
                scenario={scenario}
                systemId={systemId}
                deviceId={deviceId}
                canCreate={canCreate}
                canUpdate={canUpdate}
                canDelete={canDelete}
                canActivate={canActivate}
                onClone={(source) => {
                  setCloneSource(source)
                  setCreateOpen(true)
                }}
                onEdit={openEdit}
                onDelete={setDeleteTarget}
                onActivate={setActivateTarget}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Play}
            title="Chưa có kịch bản vận hành"
            description="Tạo kịch bản đầu tiên để cấu hình điều kiện cảnh báo cho Device."
          />
        )}
      </CardContent>

      <CreateProjectScenarioDialog
        systemId={systemId}
        deviceId={deviceId}
        scenarios={scenarios.data ?? []}
        activeScenario={activeScenario}
        cloneSource={cloneSource}
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) setCloneSource(null)
        }}
      />

      <ActivateProjectScenarioDialog
        systemId={systemId}
        deviceId={deviceId}
        currentScenario={activeScenario}
        targetScenario={activateTarget}
        open={activateTarget != null}
        onOpenChange={(open) => {
          if (!open) setActivateTarget(null)
        }}
      />

      <Dialog
        open={editTarget != null}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sửa kịch bản</DialogTitle>
            <DialogDescription>
              Đổi tên hoặc mô tả không làm thay đổi điều kiện cảnh báo đang chạy.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="edit-project-scenario-name">Tên kịch bản</Label>
              <Input
                id="edit-project-scenario-name"
                className="mt-1"
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="edit-project-scenario-description">Mô tả</Label>
              <Textarea
                id="edit-project-scenario-description"
                className="mt-1"
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
              />
            </div>
            {editMutation.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(editMutation.error)}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              Huỷ
            </Button>
            <Button
              disabled={!editName.trim() || editMutation.isPending}
              onClick={() => editMutation.mutate()}
            >
              Lưu
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xóa kịch bản?</AlertDialogTitle>
            <AlertDialogDescription>
              Kịch bản <strong>{deleteTarget?.name ?? "—"}</strong> sẽ được lưu
              lịch sử nhưng không còn xuất hiện trong danh sách vận hành.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteMutation.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(deleteMutation.error)}
            </p>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              Huỷ
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault()
                deleteMutation.mutate()
              }}
            >
              Xóa
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
