import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import type { ProjectScenarioSummary } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { createProjectScenario, queryKeys } from "@/api/resources"
import { Button } from "@/shared/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Textarea } from "@/shared/ui/textarea"

type CreateMode = "CURRENT" | "OTHER" | "BLANK"

export function CreateProjectScenarioDialog({
  systemId,
  deviceId,
  scenarios,
  activeScenario,
  cloneSource,
  open,
  onOpenChange,
  onChanged,
}: {
  systemId: string
  deviceId: string
  scenarios: ProjectScenarioSummary[]
  activeScenario: ProjectScenarioSummary | null
  cloneSource?: ProjectScenarioSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onChanged?: () => void | Promise<void>
}) {
  const client = useQueryClient()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [mode, setMode] = useState<CreateMode>("BLANK")
  const [otherScenarioId, setOtherScenarioId] = useState("")

  useEffect(() => {
    if (!open) return
    if (cloneSource) {
      setName(`${cloneSource.name} - Bản sao`)
      setDescription(cloneSource.description ?? "")
      setMode("OTHER")
      setOtherScenarioId(cloneSource.id)
      return
    }
    setName("")
    setDescription("")
    setMode(activeScenario ? "CURRENT" : "BLANK")
    setOtherScenarioId(
      scenarios.find((scenario) => !scenario.is_active)?.id ?? "",
    )
  }, [activeScenario, cloneSource, open, scenarios])

  const cloneFrom = useMemo(() => {
    if (cloneSource) return cloneSource.id
    if (mode === "CURRENT") return activeScenario?.id ?? null
    if (mode === "OTHER") return otherScenarioId || null
    return null
  }, [activeScenario, cloneSource, mode, otherScenarioId])

  const mutation = useMutation({
    mutationFn: () =>
      createProjectScenario(systemId, deviceId, {
        name: name.trim(),
        description: description.trim() || null,
        clone_from_scenario_id: cloneFrom,
      }),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: queryKeys.projectScenarios(systemId, deviceId),
      })
      await onChanged?.()
      onOpenChange(false)
    },
  })

  const valid = Boolean(name.trim()) && (mode !== "OTHER" || Boolean(cloneFrom))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {cloneSource ? "Nhân bản kịch bản" : "Tạo kịch bản"}
          </DialogTitle>
          <DialogDescription>
            Mỗi kịch bản chứa toàn bộ cảm biến và cơ cấu chấp hành của thiết bị.
            Chỉ một kịch bản được sử dụng tại một thời điểm.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="project-scenario-name">Tên kịch bản</Label>
            <Input
              id="project-scenario-name"
              className="mt-1"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ví dụ: Kịch bản mùa nóng"
              autoFocus
            />
          </div>
          <div>
            <Label htmlFor="project-scenario-description">Mô tả</Label>
            <Textarea
              id="project-scenario-description"
              className="mt-1"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Mô tả mục đích sử dụng kịch bản"
            />
          </div>

          {!cloneSource ? (
            <div>
              <Label htmlFor="project-scenario-source">Khởi tạo từ</Label>
              <select
                id="project-scenario-source"
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
                value={mode}
                onChange={(event) => setMode(event.target.value as CreateMode)}
              >
                {activeScenario ? (
                  <option value="CURRENT">Kịch bản đang sử dụng</option>
                ) : null}
                {scenarios.length ? (
                  <option value="OTHER">Kịch bản khác</option>
                ) : null}
                <option value="BLANK">Kịch bản trống</option>
              </select>
            </div>
          ) : null}

          {!cloneSource && mode === "OTHER" ? (
            <div>
              <Label htmlFor="project-scenario-other-source">Kịch bản nguồn</Label>
              <select
                id="project-scenario-other-source"
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
                value={otherScenarioId}
                onChange={(event) => setOtherScenarioId(event.target.value)}
              >
                <option value="">Chọn kịch bản</option>
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name}
                    {scenario.is_active ? " · đang sử dụng" : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {mutation.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(mutation.error)}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            type="button"
            onClick={() => onOpenChange(false)}
          >
            Huỷ
          </Button>
          <Button
            type="button"
            disabled={!valid || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {cloneSource ? "Nhân bản" : "Tạo kịch bản"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
