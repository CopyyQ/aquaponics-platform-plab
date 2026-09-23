import { useEffect, useMemo, useState } from "react"

import type {
  ProjectScenarioBranch,
  ProjectScenarioBranchCreate,
  RiskLevel,
} from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { Button } from "@/shared/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Textarea } from "@/shared/ui/textarea"

type TargetType = "SENSOR" | "ACTUATOR"
type StateChoice = "ANY" | "ON" | "OFF"
type SensorMode = "THRESHOLD" | "RANGE"
type Operator = "LT" | "LTE" | "GT" | "GTE" | "EQ"

export interface SensorConditionDraft {
  mode: SensorMode
  operator: Operator
  threshold: string
  min: string
  max: string
}

export interface ActuatorConditionDraft {
  desiredState: StateChoice
  reportedState: StateChoice
  voltageMin: string
  voltageMax: string
  currentMin: string
  currentMax: string
}

interface BranchDraft extends SensorConditionDraft, ActuatorConditionDraft {
  name: string
  riskLevel: RiskLevel
  durationSeconds: string
  isEnabled: boolean
  message: string
  consequence: string
  recommendedAction: string
}

const RISK_LEVELS: RiskLevel[] = [
  "LOW",
  "LOW_MEDIUM",
  "MEDIUM",
  "HIGH",
  "VERY_HIGH",
  "EXTREME",
]

function numeric(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function range(min: string, max: string) {
  return { min: numeric(min), max: numeric(max) }
}

function state(value: StateChoice): boolean | null {
  if (value === "ON") return true
  if (value === "OFF") return false
  return null
}

export function buildSensorCondition(draft: SensorConditionDraft): {
  evaluatorType: "THRESHOLD" | "RANGE_BANDS"
  condition: Record<string, unknown>
} {
  if (draft.mode === "THRESHOLD") {
    return {
      evaluatorType: "THRESHOLD",
      condition: {
        operator: draft.operator,
        value: numeric(draft.threshold),
      },
    }
  }
  return {
    evaluatorType: "RANGE_BANDS",
    condition: {
      range_mode: "OUTSIDE_RANGE",
      range: range(draft.min, draft.max),
    },
  }
}

export function buildActuatorCondition(
  draft: ActuatorConditionDraft,
): Record<string, unknown> {
  const voltage = range(draft.voltageMin, draft.voltageMax)
  const current = range(draft.currentMin, draft.currentMax)
  return {
    logic: "AND",
    desired_state: state(draft.desiredState),
    reported_state: state(draft.reportedState),
    voltage:
      voltage.min !== null || voltage.max !== null ? voltage : null,
    current:
      current.min !== null || current.max !== null ? current : null,
  }
}

function initialDraft(
  targetType: TargetType,
  branch: ProjectScenarioBranch | null,
): BranchDraft {
  const config = (branch?.condition_config ?? {}) as Record<string, unknown>
  const conditionRange =
    config.range && typeof config.range === "object"
      ? (config.range as Record<string, unknown>)
      : {}
  const voltage =
    config.voltage && typeof config.voltage === "object"
      ? (config.voltage as Record<string, unknown>)
      : {}
  const current =
    config.current && typeof config.current === "object"
      ? (config.current as Record<string, unknown>)
      : {}

  const choice = (value: unknown): StateChoice =>
    value === true ? "ON" : value === false ? "OFF" : "ANY"
  const text = (value: unknown) =>
    typeof value === "number" ? String(value) : ""

  return {
    name: branch?.name ?? "",
    riskLevel: branch?.business_risk_level ?? "HIGH",
    durationSeconds: String(branch?.duration_seconds ?? 0),
    isEnabled: branch?.is_enabled ?? true,
    message: branch?.message_template ?? "",
    consequence: branch?.consequence ?? "",
    recommendedAction: branch?.recommended_action ?? "",
    mode:
      targetType === "SENSOR" && branch?.evaluator_type === "RANGE_BANDS"
        ? "RANGE"
        : "THRESHOLD",
    operator:
      (config.operator as Operator | undefined) ?? "GT",
    threshold: text(config.value),
    min: text(conditionRange.min),
    max: text(conditionRange.max),
    desiredState: choice(config.desired_state),
    reportedState: choice(config.reported_state),
    voltageMin: text(voltage.min),
    voltageMax: text(voltage.max),
    currentMin: text(current.min),
    currentMax: text(current.max),
  }
}

function boundsValid(minText: string, maxText: string, requireAny: boolean) {
  const min = numeric(minText)
  const max = numeric(maxText)
  if (requireAny && min === null && max === null) return false
  if (min !== null && max !== null && min > max) return false
  return true
}

function branchPayload(
  targetType: TargetType,
  draft: BranchDraft,
): ProjectScenarioBranchCreate {
  if (targetType === "SENSOR") {
    const built = buildSensorCondition(draft)
    return {
      name: draft.name.trim(),
      evaluator_type: built.evaluatorType,
      condition_config: built.condition,
      duration_seconds: Number(draft.durationSeconds || 0),
      business_risk_level: draft.riskLevel,
      message_template: draft.message.trim() || null,
      consequence: draft.consequence.trim() || null,
      recommended_action: draft.recommendedAction.trim() || null,
      is_enabled: draft.isEnabled,
      position: 0,
    }
  }
  return {
    name: draft.name.trim(),
    evaluator_type: "MULTI_CONDITION",
    condition_config: buildActuatorCondition(draft),
    duration_seconds: Number(draft.durationSeconds || 0),
    business_risk_level: draft.riskLevel,
    message_template: draft.message.trim() || null,
    consequence: draft.consequence.trim() || null,
    recommended_action: draft.recommendedAction.trim() || null,
    is_enabled: draft.isEnabled,
    position: 0,
  }
}

export function ProjectScenarioBranchForm({
  targetType,
  initialBranch,
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  targetType: TargetType
  initialBranch: ProjectScenarioBranch | null
  pending: boolean
  error: Error | null
  onCancel: () => void
  onSubmit: (payload: ProjectScenarioBranchCreate) => void
}) {
  const [draft, setDraft] = useState<BranchDraft>(() =>
    initialDraft(targetType, initialBranch),
  )

  useEffect(() => {
    setDraft(initialDraft(targetType, initialBranch))
  }, [initialBranch, targetType])

  const conditionValid = useMemo(() => {
    if (targetType === "SENSOR") {
      if (draft.mode === "THRESHOLD") {
        return numeric(draft.threshold) !== null
      }
      return boundsValid(draft.min, draft.max, true)
    }
    const hasState =
      draft.desiredState !== "ANY" || draft.reportedState !== "ANY"
    const hasVoltage =
      numeric(draft.voltageMin) !== null || numeric(draft.voltageMax) !== null
    const hasCurrent =
      numeric(draft.currentMin) !== null || numeric(draft.currentMax) !== null
    return (
      (hasState || hasVoltage || hasCurrent) &&
      boundsValid(draft.voltageMin, draft.voltageMax, false) &&
      boundsValid(draft.currentMin, draft.currentMax, false)
    )
  }, [draft, targetType])

  const valid =
    Boolean(draft.name.trim()) &&
    Number(draft.durationSeconds) >= 0 &&
    conditionValid

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid) onSubmit(branchPayload(targetType, draft))
      }}
    >
      <div>
        <Label htmlFor="project-scenario-branch-name">Tên nhánh</Label>
        <Input
          id="project-scenario-branch-name"
          className="mt-1"
          value={draft.name}
          onChange={(event) =>
            setDraft((current) => ({ ...current, name: event.target.value }))
          }
          placeholder="Ví dụ: pH cao"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label htmlFor="project-scenario-risk">Mức rủi ro</Label>
          <select
            id="project-scenario-risk"
            className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={draft.riskLevel}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                riskLevel: event.target.value as RiskLevel,
              }))
            }
          >
            {RISK_LEVELS.map((risk) => (
              <option key={risk} value={risk}>
                {risk}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="project-scenario-duration">
            Thời gian duy trì (giây)
          </Label>
          <Input
            id="project-scenario-duration"
            className="mt-1"
            type="number"
            min={0}
            value={draft.durationSeconds}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                durationSeconds: event.target.value,
              }))
            }
          />
        </div>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={draft.isEnabled}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                isEnabled: event.target.checked,
              }))
            }
          />
          Bật nhánh
        </label>
      </div>

      <div className="rounded-lg border p-4">
        <p className="mb-3 text-sm font-medium">Điều kiện</p>
        {targetType === "SENSOR" ? (
          <SensorConditionFields draft={draft} setDraft={setDraft} />
        ) : (
          <ActuatorConditionFields draft={draft} setDraft={setDraft} />
        )}
      </div>

      <div>
        <Label htmlFor="project-scenario-telegram">
          Nội dung cảnh báo Telegram
        </Label>
        <Textarea
          id="project-scenario-telegram"
          className="mt-1"
          value={draft.message}
          onChange={(event) =>
            setDraft((current) => ({ ...current, message: event.target.value }))
          }
        />
      </div>
      <div>
        <Label htmlFor="project-scenario-consequence">Ảnh hưởng</Label>
        <Textarea
          id="project-scenario-consequence"
          className="mt-1"
          value={draft.consequence}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              consequence: event.target.value,
            }))
          }
        />
      </div>
      <div>
        <Label htmlFor="project-scenario-action">Hành động khuyến nghị</Label>
        <Textarea
          id="project-scenario-action"
          className="mt-1"
          value={draft.recommendedAction}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              recommendedAction: event.target.value,
            }))
          }
        />
      </div>

      {!conditionValid ? (
        <p className="text-sm text-amber-700">
          Hãy cấu hình ít nhất một điều kiện hợp lệ.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(error)}
        </p>
      ) : null}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Huỷ
        </Button>
        <Button type="submit" disabled={!valid || pending}>
          {initialBranch ? "Lưu nhánh" : "Thêm nhánh"}
        </Button>
      </div>
    </form>
  )
}

function SensorConditionFields({
  draft,
  setDraft,
}: {
  draft: BranchDraft
  setDraft: React.Dispatch<React.SetStateAction<BranchDraft>>
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label htmlFor="sensor-condition-mode">Kiểu điều kiện</Label>
        <select
          id="sensor-condition-mode"
          className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
          value={draft.mode}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              mode: event.target.value as SensorMode,
            }))
          }
        >
          <option value="THRESHOLD">Một ngưỡng</option>
          <option value="RANGE">Ngoài khoảng</option>
        </select>
      </div>
      {draft.mode === "THRESHOLD" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="sensor-condition-operator">Toán tử</Label>
            <select
              id="sensor-condition-operator"
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
              value={draft.operator}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  operator: event.target.value as Operator,
                }))
              }
            >
              <option value="LT">&lt;</option>
              <option value="LTE">≤</option>
              <option value="GT">&gt;</option>
              <option value="GTE">≥</option>
              <option value="EQ">=</option>
            </select>
          </div>
          <NumberInput
            label="Giá trị ngưỡng"
            value={draft.threshold}
            onChange={(threshold) =>
              setDraft((current) => ({ ...current, threshold }))
            }
          />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <NumberInput
            label="Giá trị nhỏ nhất"
            value={draft.min}
            onChange={(min) => setDraft((current) => ({ ...current, min }))}
          />
          <NumberInput
            label="Giá trị lớn nhất"
            value={draft.max}
            onChange={(max) => setDraft((current) => ({ ...current, max }))}
          />
        </div>
      )}
    </div>
  )
}

function ActuatorConditionFields({
  draft,
  setDraft,
}: {
  draft: BranchDraft
  setDraft: React.Dispatch<React.SetStateAction<BranchDraft>>
}) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Trạng thái yêu cầu chỉ là điều kiện; trạng thái vật lý vẫn dựa trên dữ
        liệu báo về/ACK và bằng chứng điện.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <StateInput
          label="Trạng thái yêu cầu"
          value={draft.desiredState}
          onChange={(desiredState) =>
            setDraft((current) => ({ ...current, desiredState }))
          }
        />
        <StateInput
          label="Trạng thái báo về"
          value={draft.reportedState}
          onChange={(reportedState) =>
            setDraft((current) => ({ ...current, reportedState }))
          }
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <NumberInput
          label="Điện áp từ (V)"
          value={draft.voltageMin}
          onChange={(voltageMin) =>
            setDraft((current) => ({ ...current, voltageMin }))
          }
        />
        <NumberInput
          label="Điện áp đến (V)"
          value={draft.voltageMax}
          onChange={(voltageMax) =>
            setDraft((current) => ({ ...current, voltageMax }))
          }
        />
        <NumberInput
          label="Dòng điện từ (A)"
          value={draft.currentMin}
          onChange={(currentMin) =>
            setDraft((current) => ({ ...current, currentMin }))
          }
        />
        <NumberInput
          label="Dòng điện đến (A)"
          value={draft.currentMax}
          onChange={(currentMax) =>
            setDraft((current) => ({ ...current, currentMax }))
          }
        />
      </div>
    </div>
  )
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div>
      <Label>{label}</Label>
      <Input
        className="mt-1"
        type="number"
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}

function StateInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: StateChoice
  onChange: (value: StateChoice) => void
}) {
  return (
    <div>
      <Label>{label}</Label>
      <select
        className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value as StateChoice)}
      >
        <option value="ANY">Không bắt buộc</option>
        <option value="ON">Bật</option>
        <option value="OFF">Tắt</option>
      </select>
    </div>
  )
}

export function ProjectScenarioBranchDialog({
  targetType,
  branch,
  open,
  pending,
  error,
  onOpenChange,
  onSubmit,
}: {
  targetType: TargetType
  branch: ProjectScenarioBranch | null
  open: boolean
  pending: boolean
  error: Error | null
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: ProjectScenarioBranchCreate) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {branch ? "Sửa nhánh cảnh báo" : "Thêm nhánh cảnh báo"}
          </DialogTitle>
          <DialogDescription>
            Nhánh thuộc kịch bản hiện tại và dùng trực tiếp cho Incident →
            Telegram khi kịch bản này đang active.
          </DialogDescription>
        </DialogHeader>
        <ProjectScenarioBranchForm
          targetType={targetType}
          initialBranch={branch}
          pending={pending}
          error={error}
          onCancel={() => onOpenChange(false)}
          onSubmit={onSubmit}
        />
      </DialogContent>
    </Dialog>
  )
}
