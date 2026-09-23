import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Boxes, Pencil, Plus, Trash2, Workflow } from "lucide-react"
import { useSearchParams } from "react-router-dom"

import {
  createScenarioCatalog,
  deleteScenarioCatalog,
  listDeviceTemplates,
  listScenarioCatalogs,
  queryKeys,
  updateScenarioCatalog,
  updateScenarioCatalogItem,
} from "@/api/resources"
import type {
  RiskLevel,
  ScenarioCatalog,
  ScenarioCatalogBranch,
  ScenarioCatalogInput,
  ScenarioCatalogItem,
} from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { CatalogsCanonicalPage } from "@/pages/catalogs-activation"
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
import { Badge } from "@/shared/ui/badge"
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
import { StatusBadge } from "@/shared/ui/status-badge"
import { Switch } from "@/shared/ui/switch"
import { Textarea } from "@/shared/ui/textarea"

type CatalogView = "home" | "devices" | "scenarios"

function resolveView(view: string | null, tab: string | null): CatalogView {
  if (view === "scenarios") return "scenarios"
  if (view === "devices" || tab === "devices" || tab === "sensors" || tab === "actuators") return "devices"
  return "home"
}

export function CatalogHubPage() {
  const [params, setParams] = useSearchParams()
  const view = resolveView(params.get("view"), params.get("tab"))
  const deviceTemplateId = Number(params.get("device")) || 0
  const templates = useQuery({ queryKey: queryKeys.templates, queryFn: listDeviceTemplates })
  const scenarios = useQuery({ queryKey: queryKeys.scenarioCatalogs, queryFn: () => listScenarioCatalogs() })
  const selectedTemplate = templates.data?.find((item) => item.id === deviceTemplateId)

  if (view === "devices") {
    return <div className="space-y-4">
      <Button type="button" variant="outline" onClick={() => setParams({})}><ArrowLeft />Danh mục</Button>
      <CatalogsCanonicalPage />
    </div>
  }

  if (view === "scenarios") {
    if (templates.isLoading) return <Skeleton className="h-96" />
    if (!selectedTemplate) return <EmptyState icon={Boxes} title="Chưa chọn thiết bị" description="Hãy quay lại Danh mục và chọn thiết bị trước khi quản lý kịch bản." />
    return <div className="space-y-6">
      <div className="flex items-start gap-3"><Button type="button" size="icon" variant="outline" aria-label="Quay lại Danh mục" onClick={() => setParams({})}><ArrowLeft /></Button><div><h1 className="text-2xl font-semibold">Kịch bản của thiết bị</h1><p className="text-sm text-muted-foreground">{selectedTemplate.name} · {selectedTemplate.code} · mỗi kịch bản chỉ thuộc thiết bị này.</p></div></div>
      <ScenarioCatalogManager deviceTemplateId={selectedTemplate.id} deviceName={selectedTemplate.name} />
    </div>
  }

  if (templates.isLoading || scenarios.isLoading) return <Skeleton className="h-96" />
  if (templates.isError) return <EmptyState icon={Boxes} title="Không thể tải thiết bị" description={errorMessage(templates.error)} />
  if (scenarios.isError) return <EmptyState icon={Workflow} title="Không thể tải kịch bản" description={errorMessage(scenarios.error)} />

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold">Danh mục</h1><p className="text-sm text-muted-foreground">Kịch bản được quản lý bên trong từng thiết bị. Một thiết bị có thể có nhiều kịch bản.</p></div><Button type="button" variant="outline" onClick={() => setParams({ view: "devices", tab: "devices" })}><Boxes />Quản lý cấu hình thiết bị</Button></div>
    {(templates.data ?? []).length ? <div className="grid gap-5 lg:grid-cols-2">{templates.data!.map((template) => {
      const deviceScenarios = (scenarios.data ?? []).filter((scenario) => scenario.device_template_id === template.id)
      return <Card key={template.id}><CardHeader><div className="flex items-start justify-between gap-3"><div><CardTitle>{template.name}</CardTitle><p className="mt-1 font-mono text-xs text-muted-foreground">{template.code}</p></div><StatusBadge value={template.is_active ? "ACTIVE" : "DISABLED"} /></div>{template.description ? <p className="text-sm text-muted-foreground">{template.description}</p> : null}</CardHeader><CardContent className="space-y-4"><div className="grid grid-cols-3 gap-3"><CatalogMetric label="Cảm biến" value={template.sensors.length} /><CatalogMetric label="Cơ cấu" value={template.actuators.length} /><CatalogMetric label="Kịch bản" value={deviceScenarios.length} /></div><div className="rounded-xl border bg-muted/30 p-4"><div className="flex items-center gap-2"><Workflow className="size-5 text-primary" /><h3 className="font-semibold">Kịch bản của thiết bị</h3></div><p className="mt-1 text-sm text-muted-foreground">Mỗi kịch bản tự chứa đầy đủ cảm biến và cơ cấu chấp hành của thiết bị này.</p><div className="mt-3 flex flex-wrap gap-2">{deviceScenarios.slice(0, 3).map((scenario) => <Badge key={scenario.id} variant="secondary">{scenario.name}</Badge>)}{deviceScenarios.length > 3 ? <Badge variant="outline">+{deviceScenarios.length - 3}</Badge> : null}{!deviceScenarios.length ? <span className="text-sm text-muted-foreground">Chưa có kịch bản.</span> : null}</div></div><Button type="button" className="w-full" onClick={() => setParams({ view: "scenarios", device: String(template.id) })}><Workflow />Mở kịch bản của thiết bị</Button></CardContent></Card>
    })}</div> : <EmptyState icon={Boxes} title="Chưa có thiết bị" description="Hãy tạo thiết bị trước. Kịch bản chỉ có thể được tạo bên trong một thiết bị." />}
  </div>
}

function CatalogMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg border bg-background p-3 text-center"><p className="text-2xl font-semibold tabular-nums">{value}</p><p className="text-xs text-muted-foreground">{label}</p></div>
}

function ScenarioCatalogManager({ deviceTemplateId, deviceName }: { deviceTemplateId: number; deviceName: string }) {
  const { can } = useAuth()
  const client = useQueryClient()
  const query = useQuery({ queryKey: queryKeys.scenarioCatalogsByTemplate(deviceTemplateId), queryFn: () => listScenarioCatalogs(deviceTemplateId) })
  const [createOpen, setCreateOpen] = useState(false)
  const [editingCatalog, setEditingCatalog] = useState<ScenarioCatalog | null>(null)
  const [editingItem, setEditingItem] = useState<{ catalog: ScenarioCatalog; item: ScenarioCatalogItem } | null>(null)
  const [deleting, setDeleting] = useState<ScenarioCatalog | null>(null)
  const [draft, setDraft] = useState<ScenarioCatalogInput>({ device_template_id: deviceTemplateId, code: "", name: "", description: null })
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.scenarioCatalogs }),
      client.invalidateQueries({ queryKey: queryKeys.scenarioCatalogsByTemplate(deviceTemplateId) }),
    ])
  }
  const create = useMutation({
    mutationFn: () => createScenarioCatalog({ device_template_id: deviceTemplateId, code: draft.code.trim().toUpperCase(), name: draft.name.trim(), description: draft.description?.trim() || null }),
    onSuccess: async () => { await refresh(); setDraft({ device_template_id: deviceTemplateId, code: "", name: "", description: null }); setCreateOpen(false) },
  })
  const remove = useMutation({ mutationFn: (id: number) => deleteScenarioCatalog(id), onSuccess: async () => { await refresh(); setDeleting(null) } })

  if (query.isLoading) return <Skeleton className="h-96" />
  if (query.isError) return <EmptyState icon={Workflow} title="Không thể tải kịch bản" description={errorMessage(query.error)} />

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Kịch bản của {deviceName}</h2><p className="text-sm text-muted-foreground">Mỗi kịch bản thuộc duy nhất thiết bị này và tự đồng bộ đầy đủ cảm biến, cơ cấu chấp hành của thiết bị.</p></div>{can("device_templates.create") ? <Button onClick={() => setCreateOpen(true)}><Plus />Tạo kịch bản</Button> : null}</div>
    {(query.data ?? []).length ? <div className="space-y-5">{query.data!.map((catalog) => <ScenarioCatalogCard key={catalog.id} catalog={catalog} canUpdate={can("device_templates.update")} canDelete={can("device_templates.delete")} onEdit={() => setEditingCatalog(catalog)} onEditItem={(item) => setEditingItem({ catalog, item })} onDelete={() => setDeleting(catalog)} />)}</div> : <EmptyState icon={Workflow} title="Chưa có kịch bản cho thiết bị" description="Tạo kịch bản đầu tiên. Backend sẽ tự đưa đầy đủ cảm biến và cơ cấu của thiết bị vào kịch bản." />}
    <ScenarioCatalogCreateDialog open={createOpen} onOpenChange={setCreateOpen} value={draft} onChange={setDraft} pending={create.isPending} error={create.error} onSubmit={() => create.mutate()} />
    {editingCatalog ? <ScenarioCatalogEditDialog catalog={editingCatalog} onClose={() => setEditingCatalog(null)} onSaved={refresh} /> : null}
    {editingItem ? <ScenarioItemDialog catalog={editingItem.catalog} item={editingItem.item} onClose={() => setEditingItem(null)} onSaved={refresh} /> : null}
    <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open) setDeleting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xóa bộ kịch bản {deleting?.name}?</AlertDialogTitle><AlertDialogDescription>Bộ kịch bản sẽ không còn xuất hiện khi tạo dự án mới. Dự án đã tạo vẫn giữ các AlertRule đã materialize.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Hủy</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={() => { if (deleting) remove.mutate(deleting.id) }}>Xóa</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>
}


function ScenarioCatalogCard({ catalog, canUpdate, canDelete, onEdit, onEditItem, onDelete }: { catalog: ScenarioCatalog; canUpdate: boolean; canDelete: boolean; onEdit: () => void; onEditItem: (item: ScenarioCatalogItem) => void; onDelete: () => void }) {
  const sensors = catalog.items.filter((item) => item.target_type === "SENSOR")
  const actuators = catalog.items.filter((item) => item.target_type === "ACTUATOR")
  const active = catalog.items.filter((item) => item.is_enabled).length
  return <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{catalog.name}</CardTitle><p className="mt-1 text-sm text-muted-foreground">{catalog.code} · {catalog.items.length} tài nguyên · {active} tài nguyên đang bật</p></div><div className="flex items-center gap-2"><StatusBadge value={catalog.is_active ? "ACTIVE" : "DISABLED"} />{canUpdate ? <Button size="sm" variant="outline" onClick={onEdit}><Pencil />Sửa bộ</Button> : null}{canDelete ? <Button size="sm" variant="ghost" onClick={onDelete}><Trash2 />Xóa</Button> : null}</div></div>{catalog.description ? <p className="text-sm text-muted-foreground">{catalog.description}</p> : null}</CardHeader><CardContent className="space-y-5"><ScenarioResourceGroup title="Cảm biến" items={sensors} canUpdate={canUpdate} onEditItem={onEditItem} /><ScenarioResourceGroup title="Cơ cấu chấp hành" items={actuators} canUpdate={canUpdate} onEditItem={onEditItem} /></CardContent></Card>
}

function ScenarioResourceGroup({ title, items, canUpdate, onEditItem }: { title: string; items: ScenarioCatalogItem[]; canUpdate: boolean; onEditItem: (item: ScenarioCatalogItem) => void }) {
  return <section className="space-y-3"><div className="flex items-center gap-2"><h3 className="font-semibold">{title}</h3><Badge variant="secondary">{items.length}</Badge></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="font-medium">{item.name}</p><p className="text-xs text-muted-foreground">{item.resource_code} · {item.model_code} · {item.branches.length} nhánh</p></div><StatusBadge value={item.is_enabled ? "ACTIVE" : "DISABLED"} /></div>{item.branches.length ? <div className="mt-3 space-y-1">{item.branches.map((branch) => <p key={branch.key} className="text-xs text-muted-foreground"><span className="font-medium text-foreground">{branch.label}</span> · {conditionSummary(branch)}{!branch.enabled ? " · Tắt" : ""}</p>)}</div> : <p className="mt-3 text-xs text-muted-foreground">Chưa có điều kiện cảnh báo.</p>}{item.notes ? <p className="mt-3 line-clamp-3 text-xs text-muted-foreground">{item.notes}</p> : null}{canUpdate ? <Button className="mt-3" size="sm" variant="outline" onClick={() => onEditItem(item)}><Pencil />Sửa kịch bản</Button> : null}</div>)}</div></section>
}

function ScenarioCatalogCreateDialog({ open, onOpenChange, value, onChange, pending, error, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; value: ScenarioCatalogInput; onChange: (value: ScenarioCatalogInput) => void; pending: boolean; error: Error | null; onSubmit: () => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Tạo bộ kịch bản</DialogTitle><DialogDescription>Backend sẽ tự đưa đầy đủ cảm biến và cơ cấu chấp hành của thiết bị này vào kịch bản.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit() }}><Field label="Mã kịch bản"><Input value={value.code} onChange={(event) => onChange({ ...value, code: event.target.value.toUpperCase() })} required /></Field><Field label="Tên bộ kịch bản"><Input value={value.name} onChange={(event) => onChange({ ...value, name: event.target.value })} required /></Field><Field label="Mô tả"><Textarea value={value.description ?? ""} onChange={(event) => onChange({ ...value, description: event.target.value })} /></Field>{error ? <p role="alert" className="text-sm text-destructive">{errorMessage(error)}</p> : null}<DialogFooter><Button type="submit" disabled={pending}>Tạo bộ kịch bản</Button></DialogFooter></form></DialogContent></Dialog>
}

function ScenarioCatalogEditDialog({ catalog, onClose, onSaved }: { catalog: ScenarioCatalog; onClose: () => void; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(catalog.name)
  const [description, setDescription] = useState(catalog.description ?? "")
  const [active, setActive] = useState(catalog.is_active)
  const update = useMutation({ mutationFn: () => updateScenarioCatalog(catalog.id, { name: name.trim(), description: description.trim() || null, is_active: active }), onSuccess: async () => { await onSaved(); onClose() } })
  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent><DialogHeader><DialogTitle>Sửa bộ kịch bản</DialogTitle><DialogDescription>Mã {catalog.code} được giữ cố định.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); update.mutate() }}><Field label="Tên"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field><Field label="Mô tả"><Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></Field><label className="flex items-center gap-2 text-sm"><Switch checked={active} onCheckedChange={setActive} />Đang hoạt động</label>{update.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(update.error)}</p> : null}<DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Hủy</Button><Button type="submit" disabled={update.isPending}>Lưu</Button></DialogFooter></form></DialogContent></Dialog>
}

const riskLevels: RiskLevel[] = ["LOW", "LOW_MEDIUM", "MEDIUM", "HIGH", "VERY_HIGH", "EXTREME"]

function cloneBranches(branches: ScenarioCatalogBranch[]): ScenarioCatalogBranch[] {
  return branches.map((branch) => ({ ...branch, condition_config: structuredClone(branch.condition_config) }))
}

function ScenarioItemDialog({ catalog, item, onClose, onSaved }: { catalog: ScenarioCatalog; item: ScenarioCatalogItem; onClose: () => void; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(item.name)
  const [enabled, setEnabled] = useState(item.is_enabled)
  const [notes, setNotes] = useState(item.notes ?? "")
  const [branches, setBranches] = useState<ScenarioCatalogBranch[]>(() => cloneBranches(item.branches))
  const save = useMutation({
    mutationFn: () => updateScenarioCatalogItem(catalog.id, item.id, { name: name.trim(), is_enabled: enabled, notes: notes.trim() || null, branches }),
    onSuccess: async () => { await onSaved(); onClose() },
  })
  const updateBranch = (index: number, branch: ScenarioCatalogBranch) => setBranches((current) => current.map((value, i) => i === index ? branch : value))
  const addBranch = () => setBranches((current) => [...current, defaultBranch(item.target_type, current.length + 1)])

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto"><DialogHeader><DialogTitle>{item.model_name}</DialogTitle><DialogDescription>{item.model_code} · {item.target_type === "SENSOR" ? "Cảm biến" : "Cơ cấu chấp hành"} · nguồn: {item.source_reference}</DialogDescription></DialogHeader><div className="space-y-5"><div className="grid gap-4 md:grid-cols-2"><Field label="Tên kịch bản"><Input value={name} onChange={(event) => setName(event.target.value)} /></Field><label className="flex items-end gap-2 pb-2 text-sm"><Switch checked={enabled} onCheckedChange={setEnabled} />Bật đánh giá kịch bản này</label></div><Field label="Ghi chú theo tài liệu"><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></Field><div className="space-y-3"><div className="flex items-center justify-between"><h3 className="font-semibold">Nhánh điều kiện</h3><Button size="sm" variant="outline" onClick={addBranch}><Plus />Thêm nhánh</Button></div>{branches.map((branch, index) => <BranchEditor key={`${branch.key}-${index}`} target={item.target_type} value={branch} onChange={(value) => updateBranch(index, value)} onDelete={() => setBranches((current) => current.filter((_, i) => i !== index))} />)}{!branches.length ? <p className="text-sm text-muted-foreground">Chưa có nhánh điều kiện. Mục vẫn xuất hiện trong catalog nhưng không sinh AlertRule.</p> : null}</div>{save.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(save.error)}</p> : null}</div><DialogFooter><Button variant="ghost" onClick={onClose}>Hủy</Button><Button onClick={() => save.mutate()} disabled={save.isPending || !name.trim()}>Lưu kịch bản</Button></DialogFooter></DialogContent></Dialog>
}


function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function numericValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function defaultBranch(target: ScenarioCatalogItem["target_type"], index: number): ScenarioCatalogBranch {
  if (target === "SENSOR") {
    return {
      key: `SENSOR_RULE_${index}`,
      label: "Điều kiện cảm biến",
      enabled: true,
      evaluator_type: "THRESHOLD",
      condition_config: { operator: "LT", value: 0, severity: "WARNING", duration_seconds: 0 },
      risk_level: "MEDIUM",
      message: null,
      consequence: null,
      recommended_action: null,
    }
  }
  return {
    key: `ACTUATOR_RULE_${index}`,
    label: "Điều kiện cơ cấu chấp hành",
    enabled: true,
    evaluator_type: "MULTI_CONDITION",
    condition_config: {
      logic: "AND",
      desired_state: true,
      reported_state: null,
      voltage: null,
      current: null,
      duration_seconds: 0,
    },
    risk_level: "MEDIUM",
    message: null,
    consequence: null,
    recommended_action: null,
  }
}

function BranchEditor({ target, value, onChange, onDelete }: { target: ScenarioCatalogItem["target_type"]; value: ScenarioCatalogBranch; onChange: (value: ScenarioCatalogBranch) => void; onDelete: () => void }) {
  return <div className="space-y-4 rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="grid flex-1 gap-3 md:grid-cols-2"><Field label="Key"><Input value={value.key} onChange={(event) => onChange({ ...value, key: event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_") })} /></Field><Field label="Tên nhánh"><Input value={value.label} onChange={(event) => onChange({ ...value, label: event.target.value })} /></Field></div><Button size="icon" variant="ghost" aria-label="Xóa nhánh" onClick={onDelete}><Trash2 /></Button></div><div className="grid gap-4 md:grid-cols-3"><label className="flex items-center gap-2 text-sm"><Switch checked={value.enabled} onCheckedChange={(enabled) => onChange({ ...value, enabled })} />Đang bật</label><Field label="Mức rủi ro"><select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={value.risk_level} onChange={(event) => onChange({ ...value, risk_level: event.target.value as RiskLevel })}>{riskLevels.map((risk) => <option key={risk} value={risk}>{risk}</option>)}</select></Field><div className="text-sm text-muted-foreground"><span className="font-medium text-foreground">Evaluator</span><p className="mt-2">{value.evaluator_type}</p></div></div>{target === "SENSOR" && value.evaluator_type === "THRESHOLD" ? <SensorThresholdCondition value={value} onChange={onChange} /> : target === "ACTUATOR" && value.evaluator_type === "MULTI_CONDITION" ? <ActuatorCondition value={value} onChange={onChange} /> : <div className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">Điều kiện nâng cao từ tài liệu được giữ nguyên: {conditionSummary(value)}</div>}<div className="grid gap-4 md:grid-cols-3"><Field label="Thông báo Telegram"><Textarea value={value.message ?? ""} onChange={(event) => onChange({ ...value, message: event.target.value || null })} /></Field><Field label="Ảnh hưởng"><Textarea value={value.consequence ?? ""} onChange={(event) => onChange({ ...value, consequence: event.target.value || null })} /></Field><Field label="Khắc phục"><Textarea value={value.recommended_action ?? ""} onChange={(event) => onChange({ ...value, recommended_action: event.target.value || null })} /></Field></div></div>
}

function SensorThresholdCondition({ value, onChange }: { value: ScenarioCatalogBranch; onChange: (value: ScenarioCatalogBranch) => void }) {
  const config = asRecord(value.condition_config)
  const operator = typeof config.operator === "string" ? config.operator : "LT"
  const threshold = numericValue(config.value) ?? 0
  const setConfig = (patch: Record<string, unknown>) => onChange({ ...value, condition_config: { ...config, ...patch } })
  return <div className="grid gap-4 md:grid-cols-3"><Field label="Điều kiện"><select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={operator} onChange={(event) => setConfig({ operator: event.target.value })}><option value="LT">Nhỏ hơn (&lt;)</option><option value="LTE">Nhỏ hơn hoặc bằng (≤)</option><option value="GT">Lớn hơn (&gt;)</option><option value="GTE">Lớn hơn hoặc bằng (≥)</option></select></Field><Field label="Ngưỡng"><Input type="number" step="any" value={threshold} onChange={(event) => setConfig({ value: Number(event.target.value) })} /></Field><Field label="Duy trì (giây)"><Input type="number" min="0" step="1" value={numericValue(config.duration_seconds) ?? 0} onChange={(event) => setConfig({ duration_seconds: Number(event.target.value) })} /></Field></div>
}

function ActuatorCondition({ value, onChange }: { value: ScenarioCatalogBranch; onChange: (value: ScenarioCatalogBranch) => void }) {
  const config = asRecord(value.condition_config)
  const voltage = asRecord(config.voltage)
  const current = asRecord(config.current)
  const desired = config.desired_state === true ? "ON" : config.desired_state === false ? "OFF" : "ANY"
  const setConfig = (patch: Record<string, unknown>) => onChange({ ...value, condition_config: { ...config, ...patch } })
  const setMetric = (key: "voltage" | "current", raw: string) => setConfig({ [key]: raw === "" ? null : { operator: "EQ", value: Number(raw) } })
  return <div className="grid gap-4 md:grid-cols-4"><Field label="Trạng thái yêu cầu"><select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={desired} onChange={(event) => setConfig({ desired_state: event.target.value === "ANY" ? null : event.target.value === "ON" })}><option value="ON">Bật</option><option value="OFF">Tắt</option><option value="ANY">Bất kỳ</option></select></Field><Field label="Điện áp tham chiếu (V)"><Input type="number" step="any" value={numericValue(voltage.value) ?? ""} onChange={(event) => setMetric("voltage", event.target.value)} /></Field><Field label="Dòng điện tham chiếu (A)"><Input type="number" step="any" value={numericValue(current.value) ?? ""} onChange={(event) => setMetric("current", event.target.value)} /></Field><Field label="Duy trì (giây)"><Input type="number" min="0" step="1" value={numericValue(config.duration_seconds) ?? 0} onChange={(event) => setConfig({ duration_seconds: Number(event.target.value) })} /></Field></div>
}

function conditionSummary(branch: ScenarioCatalogBranch): string {
  const config = asRecord(branch.condition_config)
  if (branch.evaluator_type === "THRESHOLD") {
    const operator = typeof config.operator === "string" ? config.operator : "?"
    const symbols: Record<string, string> = { LT: "<", LTE: "≤", GT: ">", GTE: "≥", EQ: "=" }
    return `${symbols[operator] ?? operator} ${String(config.value ?? "—")}`
  }
  if (branch.evaluator_type === "MULTI_CONDITION") {
    const parts: string[] = []
    if (config.desired_state === true) parts.push("Yêu cầu BẬT")
    if (config.desired_state === false) parts.push("Yêu cầu TẮT")
    const voltage = asRecord(config.voltage)
    const current = asRecord(config.current)
    if (voltage.value !== undefined) parts.push(`V = ${String(voltage.value)}`)
    if (current.value !== undefined) parts.push(`A = ${String(current.value)}`)
    return parts.join(" AND ") || "Điều kiện tổ hợp"
  }
  if (branch.evaluator_type === "THRESHOLD_BANDS") {
    const bands = Array.isArray(config.bands) ? config.bands : []
    return bands.map((band) => {
      const row = asRecord(band)
      return `${String(row.severity ?? "")} ${String(row.operator ?? "")} ${String(row.value ?? "")}`.trim()
    }).join(" / ")
  }
  return branch.evaluator_type
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><Label>{label}</Label><div className="mt-1">{children}</div></div>
}
