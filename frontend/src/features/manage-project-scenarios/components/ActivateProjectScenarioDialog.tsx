import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import type { ProjectScenarioSummary } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { activateProjectScenario, queryKeys } from "@/api/resources"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import { applyProjectScenarioActivation } from "@/features/manage-project-scenarios/model/project-scenario-activation"

export function ActivateProjectScenarioDialog({
  systemId,
  deviceId,
  currentScenario,
  targetScenario,
  open,
  onOpenChange,
  onChanged,
}: {
  systemId: string
  deviceId: string
  currentScenario: ProjectScenarioSummary | null
  targetScenario: ProjectScenarioSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onChanged?: () => void | Promise<void>
}) {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: async () => {
      if (!targetScenario) throw new Error("Chưa chọn kịch bản")
      return activateProjectScenario(systemId, deviceId, targetScenario.id)
    },
    onSuccess: (result) => {
      const scenarioListKey = queryKeys.projectScenarios(systemId, deviceId)
      client.setQueryData<ProjectScenarioSummary[]>(scenarioListKey, (current) =>
        applyProjectScenarioActivation(current, result.scenario)
      )

      onOpenChange(false)
      toast.success(`Đã chuyển sang ${result.scenario.name}`)

      void Promise.all([
        client.invalidateQueries({ queryKey: scenarioListKey }),
        client.invalidateQueries({ queryKey: queryKeys.alerts(systemId) }),
        client.invalidateQueries({ queryKey: queryKeys.activities(systemId) }),
      ]).then(async () => {
        await onChanged?.()
      })
    },
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Chuyển kịch bản đang sử dụng?</AlertDialogTitle>
          <AlertDialogDescription className="space-y-2">
            <span className="block">
              {currentScenario?.name ?? "Không có kịch bản active"} →{" "}
              <strong>{targetScenario?.name ?? "—"}</strong>
            </span>
            <span className="block">
              Các cảnh báo đang mở của kịch bản cũ sẽ được đóng với lý do{" "}
              <code>SCENARIO_CHANGED</code>.
            </span>
            <span className="block">
              Kịch bản mới sẽ được đánh giá lại ngay từ trạng thái runtime hiện
              tại. Thời gian duy trì điều kiện được tính lại từ đầu.
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        {mutation.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(mutation.error)}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Huỷ</AlertDialogCancel>
          <Button
            type="button"
            disabled={!targetScenario || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Đang chuyển..." : "Sử dụng kịch bản này"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
