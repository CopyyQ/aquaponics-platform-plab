import { BellRing, Pencil, Plus, Trash2 } from "lucide-react"

import type {
  ProjectScenarioBranch,
  ProjectScenarioItem,
} from "@/api/contracts"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"

function branchSummary(branch: ProjectScenarioBranch) {
  const config = branch.condition_config
  if (branch.evaluator_type === "THRESHOLD") {
    return `${String(config.operator ?? "")} ${String(config.value ?? "—")}`
  }
  if (
    branch.evaluator_type === "RANGE_BANDS" &&
    config.range &&
    typeof config.range === "object"
  ) {
    const bounds = config.range as Record<string, unknown>
    return `Ngoài khoảng ${String(bounds.min ?? "−∞")} → ${String(bounds.max ?? "+∞")}`
  }
  if (branch.evaluator_type === "MULTI_CONDITION") {
    const pieces: string[] = []
    if (config.desired_state !== null && config.desired_state !== undefined) {
      pieces.push(`Yêu cầu=${config.desired_state ? "BẬT" : "TẮT"}`)
    }
    if (config.reported_state !== null && config.reported_state !== undefined) {
      pieces.push(`Báo về=${config.reported_state ? "BẬT" : "TẮT"}`)
    }
    if (config.voltage) pieces.push("Điện áp")
    if (config.current) pieces.push("Dòng điện")
    return pieces.join(" · ") || "Điều kiện tổng hợp"
  }
  return branch.evaluator_type
}

export function ProjectScenarioResourceGroup({
  title,
  items,
  canWrite,
  onAdd,
  onEdit,
  onDelete,
}: {
  title: string
  items: ProjectScenarioItem[]
  canWrite: boolean
  onAdd: (item: ProjectScenarioItem) => void
  onEdit: (item: ProjectScenarioItem, branch: ProjectScenarioBranch) => void
  onDelete: (item: ProjectScenarioItem, branch: ProjectScenarioBranch) => void
}) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">
          Tất cả resource hiện có của Device đều xuất hiện trong kịch bản.
        </p>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <BellRing className="size-4 text-primary" />
                  {item.resource.name}
                </CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.resource.code} · Model #{item.resource.model_id ?? "—"}
                  {!item.is_enabled ? " · Tạm tắt trong kịch bản" : ""}
                </p>
              </div>
              {canWrite ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onAdd(item)}
                >
                  <Plus />
                  Thêm nhánh
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-3">
              {item.branches.length ? (
                item.branches.map((branch) => (
                  <div key={branch.id} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium">{branch.name}</p>
                          <span
                            className={
                              branch.is_enabled
                                ? "rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                                : "rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                            }
                          >
                            {branch.is_enabled ? "Bật" : "Tắt"}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {branchSummary(branch)} · {branch.business_risk_level}
                          {branch.duration_seconds
                            ? ` · ${branch.duration_seconds}s`
                            : ""}
                        </p>
                      </div>
                      {canWrite ? (
                        <div className="flex gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label={`Sửa nhánh ${branch.name}`}
                            onClick={() => onEdit(item, branch)}
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label={`Xóa nhánh ${branch.name}`}
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>
                                  Xóa nhánh “{branch.name}”?
                                </AlertDialogTitle>
                                <AlertDialogDescription>
                                  Nhánh sẽ ngừng đánh giá. Lịch sử Incident đã
                                  phát sinh vẫn được giữ lại.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Huỷ</AlertDialogCancel>
                                <AlertDialogAction
                                  variant="destructive"
                                  onClick={() => onDelete(item, branch)}
                                >
                                  Xóa nhánh
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      ) : null}
                    </div>
                    {branch.message_template ? (
                      <p className="mt-2 text-sm">{branch.message_template}</p>
                    ) : null}
                    {branch.consequence ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Ảnh hưởng: {branch.consequence}
                      </p>
                    ) : null}
                    {branch.recommended_action ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Khuyến nghị: {branch.recommended_action}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                  <p>Chưa cấu hình</p>
                  {canWrite ? (
                    <Button
                      className="mt-3"
                      size="sm"
                      variant="outline"
                      onClick={() => onAdd(item)}
                    >
                      <Plus />
                      Thêm nhánh
                    </Button>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
