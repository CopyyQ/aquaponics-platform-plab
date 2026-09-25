import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDownToLine, ArrowLeft, BellRing, Boxes, ChevronDown, ChevronRight, Droplet, Droplets, Eye, FilePlus, FileText, Filter, Fish, GitBranchPlus, GlassWater, Leaf, Lightbulb, Pencil, Radio, Search, Settings, Siren, Sprout, Sun, Thermometer, ThermometerSun, Trash2, Waves, Wind, Workflow, Zap } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"

import {
  createScenarioCatalog,
  deleteScenarioCatalog,
  listDeviceTemplates,
  listScenarioCatalogs,
  listSensorModels,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"
import { Switch } from "@/shared/ui/switch"
import { Textarea } from "@/shared/ui/textarea"

// Hieu ung chi ap dung cho cac hop thoai kich ban o man hinh nay.
const scenarioDialogMotion = "duration-200 ease-out data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 motion-reduce:animate-none"
const scenarioOverlayMotion = "duration-200 data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 motion-reduce:animate-none"

type ScenarioStatusFilter = "ALL" | "ACTIVE" | "DISABLED"

// Tim theo ten/ma cua Sensor va Actuator trong kich ban.
export function scenarioItemMatches(item: ScenarioCatalogItem, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase("vi")
  if (!needle) return true
  return `${item.name} ${item.resource_code} ${item.model_code} ${item.model_name}`.toLocaleLowerCase("vi").includes(needle)
}

// Don vi nguong lay tu SensorModel.unit theo sensor_model_id; Actuator khong co don vi.
function scenarioItemUnit(item: ScenarioCatalogItem, units: Map<number, string>): string | null {
  if (item.target_type !== "SENSOR" || item.sensor_model_id === null) return null
  return units.get(item.sensor_model_id)?.trim() || null
}

// Icon theo ma model; ma chua biet dung icon mac dinh cua nhom.
const resourceIcons: Record<string, LucideIcon> = {
  NH3: Droplet, NO3: Leaf, WATER_TEMPERATURE: Thermometer, WATER_LEVEL: Waves, WATER_LEVELW2: Waves, AIR_TEMPERATURE: ThermometerSun, AIR_HUMIDITY: Droplets, LIGHT_INTENSITY: Sun, VOLTAGE: Zap,
  AERATION_PUMP: Wind, FISH_TANK_PUMP: Fish, BIOFILTER_PUMP: Filter, GROW_LIGHT: Lightbulb, FILTER_DRAIN_VALVE: ArrowDownToLine, FRESH_WATER_VALVE: GlassWater, WARNING_BUZZER: BellRing, WARNING_LIGHT: Siren,
}
const resourceGlyphs: Record<string, React.ReactNode> = { PH: "pH", DO: <>O<sub className="text-[0.6em]">2</sub></>, TDS: <span className="text-[0.55rem]">TDS</span>, CURRENT: "A" }

function ScenarioResourceIcon({ item }: { item: ScenarioCatalogItem }) {
  const glyph = resourceGlyphs[item.model_code]
  const Icon = resourceIcons[item.model_code] ?? (item.target_type === "SENSOR" ? Radio : Settings)
  return <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">{glyph ?? <Icon className="size-4" />}</span>
}

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
  const [templateSearch, setTemplateSearch] = useState("")
  const [templateStatus, setTemplateStatus] = useState<ScenarioStatusFilter>("ALL")

  if (view === "devices") {
    return <div className="space-y-4">
      {selectedTemplate ? <Button hidden type="button" variant="outline" onClick={() => setParams({ view: "scenarios", device: String(selectedTemplate.id) })}><ArrowLeft />Kịch bản thiết bị</Button> : <Button type="button" variant="outline" onClick={() => setParams({})}><ArrowLeft />Danh mục</Button>}
      <CatalogsCanonicalPage />
    </div>
  }

  if (view === "scenarios") {
    if (templates.isLoading) return <Skeleton className="h-96" />
    if (!selectedTemplate) return <EmptyState icon={Boxes} title="Chưa chọn thiết bị" description="Hãy quay lại Danh mục và chọn thiết bị trước khi quản lý kịch bản." />
    return <ScenarioCatalogManager deviceTemplateId={selectedTemplate.id} />
  }

  if (templates.isLoading || scenarios.isLoading) return <Skeleton className="h-96" />
  if (templates.isError) return <EmptyState icon={Boxes} title="Không thể tải thiết bị" description={errorMessage(templates.error)} />
  if (scenarios.isError) return <EmptyState icon={Workflow} title="Không thể tải kịch bản" description={errorMessage(scenarios.error)} />

  const allTemplates = templates.data ?? []
  const needle = templateSearch.trim().toLocaleLowerCase("vi")
  const visibleTemplates = allTemplates.filter((template) => (!needle || `${template.name} ${template.code} ${template.description ?? ""}`.toLocaleLowerCase("vi").includes(needle)) && (templateStatus === "ALL" || (templateStatus === "ACTIVE" ? template.is_active : !template.is_active)))

  return <div className="space-y-6">
    <div className="space-y-3"><div><h1 className="text-3xl font-bold">Danh mục</h1><p className="text-sm text-muted-foreground">Kịch bản được quản lý bên trong từng thiết bị. Một thiết bị có thể có nhiều kịch bản.</p></div><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex w-full flex-wrap items-center gap-3 sm:w-auto"><label className="relative block w-full shrink-0 sm:w-80"><span className="sr-only">Tìm thiết bị</span><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input className="pl-9" placeholder="Tìm thiết bị theo tên hoặc mã thiết bị" value={templateSearch} onChange={(event) => setTemplateSearch(event.target.value)} /></label><Select value={templateStatus} onValueChange={(value) => setTemplateStatus(value as ScenarioStatusFilter)}><SelectTrigger aria-label="Lọc thiết bị theo trạng thái" className="w-auto shrink-0 gap-2 text-sm"><SelectValue /></SelectTrigger><SelectContent position="popper" sideOffset={6} className="w-auto min-w-[var(--radix-select-trigger-width)] whitespace-nowrap"><SelectItem value="ALL">Tất cả trạng thái</SelectItem><SelectItem value="ACTIVE">Đang hoạt động</SelectItem><SelectItem value="DISABLED">Đã vô hiệu hóa</SelectItem></SelectContent></Select></div><Button hidden type="button" variant="outline" onClick={() => setParams({ view: "devices", tab: "devices" })}><Boxes />Quản lý cấu hình thiết bị</Button></div></div>
    {visibleTemplates.length ? <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">{visibleTemplates.map((template) => {
      const deviceScenarios = (scenarios.data ?? []).filter((scenario) => scenario.device_template_id === template.id)
      return <Card key={template.id}><CardHeader className="p-4"><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sprout className="size-5" /></span><div className="min-w-0"><CardTitle>{template.name}</CardTitle><p className="mt-1 font-mono text-xs text-muted-foreground">{template.code}</p></div></div><StatusBadge className="shrink-0 whitespace-nowrap" value={template.is_active ? "ACTIVE" : "DISABLED"} /></div>{template.description ? <p className="line-clamp-2 text-sm text-muted-foreground" title={template.description}>{template.description}</p> : null}</CardHeader><CardContent className="space-y-3 p-4 pt-0"><div className="grid grid-cols-3 gap-2"><CatalogMetric icon={Radio} label="Cảm biến" value={template.sensors.length} /><CatalogMetric icon={Settings} label="Cơ cấu" value={template.actuators.length} /><CatalogMetric icon={FileText} label="Kịch bản" value={deviceScenarios.length} /></div><div hidden className="rounded-xl border bg-muted/30 p-4"><div className="flex items-center gap-2"><Workflow className="size-5 text-primary" /><h3 className="font-semibold">Kịch bản của thiết bị</h3></div><p className="mt-1 text-sm text-muted-foreground">Mỗi kịch bản tự chứa đầy đủ cảm biến và cơ cấu chấp hành của thiết bị này.</p><div className="mt-3 flex flex-wrap gap-2">{deviceScenarios.slice(0, 3).map((scenario) => <Badge key={scenario.id} variant="secondary">{scenario.name}</Badge>)}{deviceScenarios.length > 3 ? <Badge variant="outline">+{deviceScenarios.length - 3}</Badge> : null}{!deviceScenarios.length ? <span className="text-sm text-muted-foreground">Chưa có kịch bản.</span> : null}</div></div><Button type="button" className="w-full" onClick={() => setParams({ view: "scenarios", device: String(template.id) })}><Workflow />Mở kịch bản của thiết bị</Button></CardContent></Card>
    })}</div> : allTemplates.length ? <EmptyState icon={Boxes} title="Không tìm thấy thiết bị" description="Thử từ khoá hoặc trạng thái khác." /> : <EmptyState icon={Boxes} title="Chưa có thiết bị" description="Hãy tạo thiết bị trước. Kịch bản chỉ có thể được tạo bên trong một thiết bị." />}
  </div>
}

function CatalogMetric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number }) {
  return <div className="flex items-center gap-2 rounded-lg border bg-background px-2.5 py-2"><span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"><Icon className="size-4" /></span><div className="min-w-0"><p className="text-xl font-semibold leading-tight tabular-nums">{value}</p><p className="truncate text-xs text-muted-foreground">{label}</p></div></div>
}

function ScenarioCatalogManager({ deviceTemplateId }: { deviceTemplateId: number }) {
  const { can } = useAuth()
  const [, setParams] = useSearchParams()
  const client = useQueryClient()
  const query = useQuery({ queryKey: queryKeys.scenarioCatalogsByTemplate(deviceTemplateId), queryFn: () => listScenarioCatalogs(deviceTemplateId) })
  const sensorModels = useQuery({ queryKey: queryKeys.sensorModels, queryFn: listSensorModels })
  const units = new Map((sensorModels.data ?? []).map((model) => [model.id, model.unit]))
  const [search, setSearch] = useState("")
  const [catalogStatus, setCatalogStatus] = useState<ScenarioStatusFilter>("ALL")
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
    onSuccess: async () => { await refresh(); setDraft({ device_template_id: deviceTemplateId, code: "", name: "", description: null }); setCreateOpen(false); toast.success("Tạo kịch bản thành công", { duration: 4000 }) },
  })
  const remove = useMutation({ mutationFn: (id: number) => deleteScenarioCatalog(id), onSuccess: async () => { await refresh(); setDeleting(null); toast.error("Xóa kịch bản thiết bị thành công", { duration: 4000 }) } })

  if (query.isLoading) return <Skeleton className="h-96" />
  if (query.isError) return <EmptyState icon={Workflow} title="Không thể tải kịch bản" description={errorMessage(query.error)} />

  const catalogs = query.data ?? []
  const searching = Boolean(search.trim())
  const visible = catalogs.filter((catalog) => (!searching || catalog.items.some((item) => scenarioItemMatches(item, search))) && (catalogStatus === "ALL" || (catalogStatus === "ACTIVE" ? catalog.is_active : !catalog.is_active)))

  return <div className="space-y-5">
    <div className="space-y-3"><h1 className="flex items-center gap-3 text-3xl font-bold"><Sprout aria-hidden className="size-8 text-primary" />Kịch bản thiết bị</h1><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex w-full flex-wrap items-center gap-3 sm:w-auto"><label className="relative block w-full shrink-0 sm:w-80"><span className="sr-only">Tìm cảm biến hoặc cơ cấu chấp hành</span><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input className="pl-9" placeholder="Tìm cảm biến, cơ cấu chấp hành" value={search} onChange={(event) => setSearch(event.target.value)} /></label><Select value={catalogStatus} onValueChange={(value) => setCatalogStatus(value as ScenarioStatusFilter)}><SelectTrigger aria-label="Lọc kịch bản theo trạng thái" className="w-auto shrink-0 gap-2 text-sm"><SelectValue /></SelectTrigger><SelectContent position="popper" sideOffset={6} className="w-auto min-w-[var(--radix-select-trigger-width)] whitespace-nowrap"><SelectItem value="ALL">Tất cả kịch bản</SelectItem><SelectItem value="ACTIVE">Đang hoạt động</SelectItem><SelectItem value="DISABLED">Đã vô hiệu hóa</SelectItem></SelectContent></Select></div><div className="flex flex-wrap items-center gap-3"><Button type="button" variant="outline" onClick={() => setParams({ view: "devices", tab: "devices", device: String(deviceTemplateId) })}><Boxes />Quản lý cấu hình thiết bị</Button>{can("device_templates.create") ? <Button onClick={() => setCreateOpen(true)}><FilePlus />Tạo kịch bản</Button> : null}</div></div></div>
    {visible.length ? <div className="space-y-5">{visible.map((catalog) => <ScenarioCatalogCard key={catalog.id} catalog={catalog} canUpdate={can("device_templates.update")} canDelete={can("device_templates.delete")} onEdit={() => setEditingCatalog(catalog)} onEditItem={(item) => setEditingItem({ catalog, item })} onDelete={() => setDeleting(catalog)} search={search} units={units} />)}</div> : catalogs.length ? <EmptyState icon={Workflow} title={searching ? "Không tìm thấy cảm biến hoặc cơ cấu chấp hành" : "Không có kịch bản phù hợp"} description="Thử từ khoá hoặc trạng thái khác để xem lại toàn bộ kịch bản." /> : <EmptyState icon={Workflow} title="Chưa có kịch bản cho thiết bị" description="Tạo kịch bản đầu tiên. Backend sẽ tự đưa đầy đủ cảm biến và cơ cấu của thiết bị vào kịch bản." />}
    <ScenarioCatalogCreateDialog open={createOpen} onOpenChange={setCreateOpen} value={draft} onChange={setDraft} pending={create.isPending} error={create.error} onSubmit={() => create.mutate()} />
    {editingCatalog ? <ScenarioCatalogEditDialog catalog={editingCatalog} onClose={() => setEditingCatalog(null)} onSaved={refresh} /> : null}
    {editingItem ? <ScenarioItemDialog catalog={editingItem.catalog} item={editingItem.item} unit={scenarioItemUnit(editingItem.item, units)} onClose={() => setEditingItem(null)} onSaved={refresh} /> : null}
    <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open) setDeleting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xóa bộ kịch bản {deleting?.name}?</AlertDialogTitle><AlertDialogDescription>Kịch bản sẽ không còn được sử dụng khi tạo dự án mới. Các dự án đã tạo trước đó vẫn giữ nguyên các thiết lập cảnh báo và không bị ảnh hưởng.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Hủy</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={() => { if (deleting) remove.mutate(deleting.id) }}>Xóa</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>
}


function ScenarioCatalogCard({ catalog, canUpdate, canDelete, onEdit, onEditItem, onDelete, search, units }: { catalog: ScenarioCatalog; canUpdate: boolean; canDelete: boolean; onEdit: () => void; onEditItem: (item: ScenarioCatalogItem) => void; onDelete: () => void; search: string; units: Map<number, string> }) {
  const [status, setStatus] = useState<ScenarioStatusFilter>("ALL")
  const searching = Boolean(search.trim())
  const matching = catalog.items.filter((item) => scenarioItemMatches(item, search) && (status === "ALL" || (status === "ACTIVE" ? item.is_enabled : !item.is_enabled)))
  const sensors = matching.filter((item) => item.target_type === "SENSOR")
  const actuators = matching.filter((item) => item.target_type === "ACTUATOR")
  const active = catalog.items.filter((item) => item.is_enabled).length
  const [groupsOpen, setGroupsOpen] = useState({ sensor: false, actuator: false })
  return <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{catalog.name}</CardTitle><p className="mt-1 text-sm text-muted-foreground">{catalog.code} · {catalog.items.length} tài nguyên · {active} tài nguyên đang bật</p></div><div className="flex flex-wrap items-center gap-2"><StatusBadge className="h-8 shrink-0 whitespace-nowrap rounded-md px-3 font-medium" value={catalog.is_active ? "ACTIVE" : "DISABLED"} /><Select value={status} onValueChange={(value) => setStatus(value as ScenarioStatusFilter)}><SelectTrigger aria-label={`Lọc tài nguyên theo trạng thái trong ${catalog.name}`} className="h-8 w-auto shrink-0 gap-2 text-sm"><SelectValue /></SelectTrigger><SelectContent position="popper" sideOffset={6} className="w-auto min-w-[var(--radix-select-trigger-width)] whitespace-nowrap"><SelectItem value="ALL">Tất cả trạng thái</SelectItem><SelectItem value="ACTIVE">Đang hoạt động</SelectItem><SelectItem value="DISABLED">Đã vô hiệu hóa</SelectItem></SelectContent></Select>{canUpdate ? <Button size="sm" variant="outline" onClick={onEdit}><Pencil />Sửa bộ</Button> : null}{canDelete ? <Button size="sm" variant="outline" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive dark:bg-transparent dark:hover:bg-destructive/15" onClick={onDelete}><Trash2 />Xóa</Button> : null}</div></div>{catalog.description ? <p className="text-sm text-muted-foreground">{catalog.description}</p> : null}</CardHeader><CardContent className="space-y-3"><ScenarioResourceGroup title="Cảm biến" icon={Radio} items={sensors} units={units} canUpdate={canUpdate} open={searching || status !== "ALL" || groupsOpen.sensor} onToggle={() => setGroupsOpen((current) => ({ ...current, sensor: !current.sensor }))} onEditItem={onEditItem} /><ScenarioResourceGroup title="Cơ cấu chấp hành" icon={Settings} items={actuators} units={units} canUpdate={canUpdate} open={searching || status !== "ALL" || groupsOpen.actuator} onToggle={() => setGroupsOpen((current) => ({ ...current, actuator: !current.actuator }))} onEditItem={onEditItem} /></CardContent></Card>
}

function ScenarioResourceGroup({ title, icon: GroupIcon, items, units, canUpdate, open, onToggle, onEditItem }: { title: string; icon: LucideIcon; items: ScenarioCatalogItem[]; units: Map<number, string>; canUpdate: boolean; open: boolean; onToggle: () => void; onEditItem: (item: ScenarioCatalogItem) => void }) {
  return <section className="overflow-hidden rounded-xl border bg-muted/30"><button type="button" aria-expanded={open} className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left transition-colors duration-150 hover:bg-muted/60 motion-reduce:transition-none" onClick={onToggle}><span className="flex items-center gap-2 text-sm font-semibold">{open ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}<GroupIcon aria-hidden className="size-4 text-primary" />{title}</span><Badge variant="secondary">{items.length}</Badge></button>{open ? <div className="grid gap-3 border-t bg-background/60 p-4 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => <div key={item.id} className="rounded-xl border bg-white p-4 dark:bg-card"><div className="flex items-start justify-between gap-2"><div className="flex min-w-0 items-start gap-3"><ScenarioResourceIcon item={item} /><div className="min-w-0"><p className="font-medium">{item.name}</p><p className="text-xs text-muted-foreground">{item.resource_code} · {item.model_code} · {item.branches.length} nhánh</p></div></div><div className="flex shrink-0 items-center gap-2"><StatusBadge value={item.is_enabled ? "ACTIVE" : "DISABLED"} />{canUpdate ? <Button size="icon-sm" variant="outline" aria-label={`Xem kịch bản ${item.name}`} title={`Xem kịch bản ${item.name}`} onClick={() => onEditItem(item)}><Eye /></Button> : null}</div></div>{item.branches.length ? <div className="mt-3 space-y-1">{item.branches.map((branch) => <p key={branch.key} className="text-xs text-muted-foreground"><span className="font-medium text-foreground">{branch.label}</span> · {conditionSummary(branch, scenarioItemUnit(item, units))}{!branch.enabled ? " · Tắt" : ""}</p>)}</div> : <p className="mt-3 text-xs text-muted-foreground">Chưa có điều kiện cảnh báo.</p>}{item.notes ? <p hidden className="mt-3 line-clamp-3 text-xs text-muted-foreground">{item.notes}</p> : null}</div>)}</div> : null}</section>
}

function ScenarioCatalogCreateDialog({ open, onOpenChange, value, onChange, pending, error, onSubmit }: { open: boolean; onOpenChange: (open: boolean) => void; value: ScenarioCatalogInput; onChange: (value: ScenarioCatalogInput) => void; pending: boolean; error: Error | null; onSubmit: () => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className={scenarioDialogMotion} overlayClassName={scenarioOverlayMotion}><DialogHeader><DialogTitle>Tạo bộ kịch bản</DialogTitle><DialogDescription>Các cảm biến và thiết bị chấp hành của hệ thống sẽ được tự động thêm vào kịch bản.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit() }}><Field label="Mã kịch bản"><Input value={value.code} onChange={(event) => onChange({ ...value, code: event.target.value.toUpperCase() })} required /></Field><Field label="Tên bộ kịch bản"><Input value={value.name} onChange={(event) => onChange({ ...value, name: event.target.value })} required /></Field><Field label="Mô tả"><Textarea value={value.description ?? ""} onChange={(event) => onChange({ ...value, description: event.target.value })} /></Field>{error ? <p role="alert" className="text-sm text-destructive">{errorMessage(error)}</p> : null}<DialogFooter><Button type="submit" disabled={pending}>Tạo bộ kịch bản</Button></DialogFooter></form></DialogContent></Dialog>
}

function ScenarioCatalogEditDialog({ catalog, onClose, onSaved }: { catalog: ScenarioCatalog; onClose: () => void; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(catalog.name)
  const [description, setDescription] = useState(catalog.description ?? "")
  const [active, setActive] = useState(catalog.is_active)
  const update = useMutation({ mutationFn: () => updateScenarioCatalog(catalog.id, { name: name.trim(), description: description.trim() || null, is_active: active }), onSuccess: async () => { await onSaved(); onClose() } })
  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className={scenarioDialogMotion} overlayClassName={scenarioOverlayMotion}><DialogHeader><DialogTitle>Sửa bộ kịch bản</DialogTitle><DialogDescription>Mã {catalog.code} được giữ cố định.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); update.mutate() }}><Field label="Tên"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field><Field label="Mô tả"><Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></Field><label className="flex items-center gap-2 text-sm"><Switch checked={active} onCheckedChange={setActive} />Đang hoạt động</label>{update.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(update.error)}</p> : null}<DialogFooter><Button type="button" variant="ghost" onClick={onClose}>Hủy</Button><Button type="submit" disabled={update.isPending}>Lưu</Button></DialogFooter></form></DialogContent></Dialog>
}

const riskLevels: RiskLevel[] = ["LOW", "LOW_MEDIUM", "MEDIUM", "HIGH", "VERY_HIGH", "EXTREME"]
const riskLabels: Record<RiskLevel, string> = { LOW: "Thấp", LOW_MEDIUM: "Thấp – trung bình", MEDIUM: "Trung bình", HIGH: "Cao", VERY_HIGH: "Rất cao", EXTREME: "Cực cao" }

function cloneBranch(branch: ScenarioCatalogBranch): ScenarioCatalogBranch {
  return { ...branch, condition_config: structuredClone(branch.condition_config) }
}

function cloneBranches(branches: ScenarioCatalogBranch[]): ScenarioCatalogBranch[] {
  return branches.map(cloneBranch)
}

export function nextBranchIndex(target: ScenarioCatalogItem["target_type"], branches: ScenarioCatalogBranch[]): number {
  const prefix = target === "SENSOR" ? "SENSOR_RULE_" : "ACTUATOR_RULE_"
  const used = new Set(branches.map((branch) => branch.key))
  let index = branches.length + 1
  while (used.has(`${prefix}${index}`)) index += 1
  return index
}

function ScenarioItemDialog({ catalog, item, unit, onClose, onSaved }: { catalog: ScenarioCatalog; item: ScenarioCatalogItem; unit: string | null; onClose: () => void; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(item.name)
  const [enabled, setEnabled] = useState(item.is_enabled)
  const [notes, setNotes] = useState(item.notes ?? "")
  const [branches, setBranches] = useState<ScenarioCatalogBranch[]>(() => cloneBranches(item.branches))
  const save = useMutation({
    mutationFn: () => updateScenarioCatalogItem(catalog.id, item.id, { name: name.trim(), is_enabled: enabled, notes: notes.trim() || null, branches }),
    onSuccess: async () => { await onSaved(); onClose() },
  })
  const [branchDraft, setBranchDraft] = useState<{ index: number | null; value: ScenarioCatalogBranch } | null>(null)
  const [deletingBranch, setDeletingBranch] = useState<number | null>(null)
  const openBranchCreate = () => setBranchDraft({ index: null, value: defaultBranch(item.target_type, nextBranchIndex(item.target_type, branches)) })
  const commitBranch = (branch: ScenarioCatalogBranch) => {
    const draft = branchDraft
    if (!draft) return
    setBranches((current) => draft.index === null ? [...current, branch] : current.map((value, i) => i === draft.index ? branch : value))
    setBranchDraft(null)
    if (draft.index === null) toast.success("Thêm nhánh thành công", { duration: 4000 })
  }
  const branchPendingDelete = deletingBranch === null ? null : branches[deletingBranch] ?? null
  const removeBranch = () => {
    const index = deletingBranch
    if (index === null) return
    setBranches((current) => current.filter((_, i) => i !== index))
    setDeletingBranch(null)
    toast.success("Xóa nhánh thành công", { duration: 4000 })
  }

  return <Dialog open onOpenChange={(open) => { if (!open) onClose() }}><DialogContent className={`max-h-[90vh] max-w-4xl overflow-y-auto ${scenarioDialogMotion}`} overlayClassName={scenarioOverlayMotion}><DialogHeader><DialogTitle>{item.model_name}</DialogTitle><DialogDescription>{item.model_code} · {item.target_type === "SENSOR" ? "Cảm biến" : "Cơ cấu chấp hành"} · nguồn: {item.source_reference}</DialogDescription></DialogHeader><div className="space-y-5"><div className="grid gap-4 md:grid-cols-2"><Field label="Tên kịch bản"><Input value={name} onChange={(event) => setName(event.target.value)} /></Field><label className="flex items-end gap-2 pb-2 text-sm"><Switch checked={enabled} onCheckedChange={setEnabled} />Bật đánh giá kịch bản</label></div><Field label="Ghi chú theo tài liệu"><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></Field><div className="space-y-3"><div className="flex items-center justify-between"><h3 className="font-semibold">Nhánh điều kiện</h3><Button size="sm" onClick={openBranchCreate}><GitBranchPlus />Thêm</Button></div>{branches.map((branch, index) => <BranchSummaryRow key={`${branch.key}-${index}`} branch={branch} unit={unit} onEdit={() => setBranchDraft({ index, value: cloneBranch(branch) })} onDelete={() => setDeletingBranch(index)} />)}{!branches.length ? <p className="text-sm text-muted-foreground">Chưa có nhánh điều kiện. Mục vẫn xuất hiện trong catalog nhưng không sinh AlertRule.</p> : null}</div>{save.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(save.error)}</p> : null}</div><DialogFooter><Button onClick={() => save.mutate()} disabled={save.isPending || !name.trim()}>Lưu</Button></DialogFooter>{branchDraft ? <BranchDialog target={item.target_type} unit={unit} draft={branchDraft} reservedKeys={branches.filter((_, i) => i !== branchDraft.index).map((branch) => branch.key)} onCancel={() => setBranchDraft(null)} onSubmit={commitBranch} /> : null}<AlertDialog open={branchPendingDelete !== null} onOpenChange={(open) => { if (!open) setDeletingBranch(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xóa nhánh {branchPendingDelete?.label.trim() || branchPendingDelete?.key}?</AlertDialogTitle><AlertDialogDescription>Nhánh {branchPendingDelete?.key} sẽ bị bỏ khỏi danh sách nhánh điều kiện. Kịch bản chỉ được ghi lại khi bạn bấm Lưu.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Hủy</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={removeBranch}>Xóa</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog></DialogContent></Dialog>
}

const operatorLabels: Record<string, string> = { LT: "Nhỏ hơn", LTE: "Nhỏ hơn hoặc bằng", GT: "Lớn hơn", GTE: "Lớn hơn hoặc bằng", EQ: "Bằng" }

// Nhanh hien thi day du nhung chi doc; muon sua thi mo modal.
function BranchSummaryRow({ branch, unit, onEdit, onDelete }: { branch: ScenarioCatalogBranch; unit: string | null; onEdit: () => void; onDelete: () => void }) {
  const title = branch.label.trim() || branch.key
  return <div className="space-y-4 rounded-xl border p-4 transition-colors duration-150 hover:border-primary/40 motion-reduce:transition-none">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><StatusBadge value={branch.enabled ? "ACTIVE" : "DISABLED"} /><p className="mt-2 font-medium">{title}</p><p className="mt-1 text-xs text-muted-foreground">{branch.key} · {branch.evaluator_type}</p></div><div className="flex items-center gap-2"><Button size="sm" variant="outline" onClick={onEdit}><Pencil />Sửa</Button><Button size="sm" variant="outline" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive dark:bg-transparent dark:hover:bg-destructive/15" aria-label={`Xóa nhánh ${title}`} onClick={onDelete}><Trash2 />Xóa</Button></div></div>
    <BranchDetails branch={branch} unit={unit} />
  </div>
}

function BranchDetails({ branch, unit }: { branch: ScenarioCatalogBranch; unit: string | null }) {
  const config = asRecord(branch.condition_config)
  const duration = `${numericValue(config.duration_seconds) ?? 0} giây`
  let condition = null
  if (branch.evaluator_type === "THRESHOLD") {
    const operator = typeof config.operator === "string" ? config.operator : ""
    condition = <><ReadOnlyField label="Điều kiện" value={operatorLabels[operator] ?? operator ?? "—"} /><ReadOnlyField label="Ngưỡng" value={withUnit(config.value, unit)} /><ReadOnlyField label="Duy trì" value={duration} /></>
  } else if (branch.evaluator_type === "MULTI_CONDITION") {
    const voltage = asRecord(config.voltage)
    const current = asRecord(config.current)
    const desired = config.desired_state === true ? "Bật" : config.desired_state === false ? "Tắt" : "Bất kỳ"
    condition = <><ReadOnlyField label="Trạng thái yêu cầu" value={desired} /><ReadOnlyField label="Điện áp tham chiếu (V)" value={numericValue(voltage.value) === null ? "Không dùng" : String(voltage.value)} /><ReadOnlyField label="Dòng điện tham chiếu (A)" value={numericValue(current.value) === null ? "Không dùng" : String(current.value)} /><ReadOnlyField label="Duy trì" value={duration} /></>
  } else {
    condition = <ReadOnlyField label="Điều kiện nâng cao" value={conditionSummary(branch, unit)} />
  }
  // Ba nhom dung chung mot luoi 3 cot de moc cot thang hang tu tren xuong.
  const row = "grid grid-cols-1 items-start gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-3"
  return <div className="space-y-4 border-t pt-4">
    <div className={row}>{condition}</div>
    <div className={row}><ReadOnlyField label="Mức rủi ro" value={riskLabels[branch.risk_level] ?? branch.risk_level} /><ReadOnlyField label="Trạng thái" value={branch.enabled ? "Đang bật" : "Đang tắt"} /></div>
    <div className={row}><ReadOnlyField label="Thông báo Telegram" value={branch.message} /><ReadOnlyField label="Ảnh hưởng" value={branch.consequence} /><ReadOnlyField label="Khắc phục" value={branch.recommended_action} /></div>
  </div>
}

function ReadOnlyField({ label, value }: { label: string; value: string | null }) {
  return <div className="min-w-0"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 whitespace-pre-line break-words text-sm">{value?.trim() ? value : "—"}</p></div>
}

function BranchDialog({ target, unit, draft, reservedKeys, onCancel, onSubmit }: { target: ScenarioCatalogItem["target_type"]; unit: string | null; draft: { index: number | null; value: ScenarioCatalogBranch }; reservedKeys: string[]; onCancel: () => void; onSubmit: (branch: ScenarioCatalogBranch) => void }) {
  const [value, setValue] = useState(draft.value)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const key = value.key.trim()
  const duplicateKey = reservedKeys.includes(key)
  const invalid = !key || !value.label.trim() || duplicateKey
  const title = value.label.trim() || key
  const submit = () => onSubmit({ ...value, key })
  return <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}><DialogContent className={`max-h-[90vh] max-w-3xl overflow-y-auto ${scenarioDialogMotion}`} overlayClassName={scenarioOverlayMotion}><DialogHeader><DialogTitle>{draft.index === null ? "Thêm nhánh điều kiện" : "Sửa nhánh điều kiện"}</DialogTitle><DialogDescription>Nhánh chỉ được ghi vào kịch bản sau khi bạn bấm Lưu ở hộp thoại trước.</DialogDescription></DialogHeader><BranchEditor target={target} unit={unit} value={value} onChange={setValue} />{duplicateKey ? <p role="alert" className="text-sm text-destructive">Key {key} đã được dùng cho nhánh khác.</p> : null}<DialogFooter><Button variant="ghost" onClick={onCancel}>Hủy</Button><Button onClick={() => { if (draft.index === null) setConfirmOpen(true); else submit() }} disabled={invalid}>{draft.index === null ? "Thêm" : "Lưu"}</Button></DialogFooter><AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Bạn có muốn thêm nhánh này không?</AlertDialogTitle><AlertDialogDescription>Nhánh {title} ({key}) sẽ được thêm vào danh sách nhánh điều kiện.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Hủy</AlertDialogCancel><AlertDialogAction onClick={submit}>Xác nhận</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog></DialogContent></Dialog>
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

function BranchEditor({ target, unit, value, onChange }: { target: ScenarioCatalogItem["target_type"]; unit: string | null; value: ScenarioCatalogBranch; onChange: (value: ScenarioCatalogBranch) => void }) {
  return <div className="space-y-4"><div className="grid gap-3 md:grid-cols-2"><Field label="Key"><Input value={value.key} onChange={(event) => onChange({ ...value, key: event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_") })} /></Field><Field label="Tên nhánh"><Input value={value.label} onChange={(event) => onChange({ ...value, label: event.target.value })} /></Field></div>{target === "SENSOR" && value.evaluator_type === "THRESHOLD" ? <SensorThresholdCondition unit={unit} value={value} onChange={onChange} /> : target === "ACTUATOR" && value.evaluator_type === "MULTI_CONDITION" ? <ActuatorCondition value={value} onChange={onChange} /> : <div className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">Điều kiện nâng cao từ tài liệu được giữ nguyên: {conditionSummary(value, unit)}</div>}<div className="grid gap-4 md:grid-cols-3"><Field label="Mức rủi ro"><select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={value.risk_level} onChange={(event) => onChange({ ...value, risk_level: event.target.value as RiskLevel })}>{riskLevels.map((risk) => <option key={risk} value={risk}>{riskLabels[risk]}</option>)}</select></Field><label className="flex items-end gap-2 pb-2 text-sm"><Switch checked={value.enabled} onCheckedChange={(enabled) => onChange({ ...value, enabled })} />Đang bật</label></div><div className="grid gap-4 md:grid-cols-3"><Field label="Thông báo Telegram"><Textarea value={value.message ?? ""} onChange={(event) => onChange({ ...value, message: event.target.value || null })} /></Field><Field label="Ảnh hưởng"><Textarea value={value.consequence ?? ""} onChange={(event) => onChange({ ...value, consequence: event.target.value || null })} /></Field><Field label="Khắc phục"><Textarea value={value.recommended_action ?? ""} onChange={(event) => onChange({ ...value, recommended_action: event.target.value || null })} /></Field></div></div>
}

function SensorThresholdCondition({ unit, value, onChange }: { unit: string | null; value: ScenarioCatalogBranch; onChange: (value: ScenarioCatalogBranch) => void }) {
  const config = asRecord(value.condition_config)
  const operator = typeof config.operator === "string" ? config.operator : "LT"
  const threshold = numericValue(config.value) ?? 0
  const setConfig = (patch: Record<string, unknown>) => onChange({ ...value, condition_config: { ...config, ...patch } })
  return <div className="grid gap-4 md:grid-cols-3"><Field label="Điều kiện"><select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={operator} onChange={(event) => setConfig({ operator: event.target.value })}><option value="LT">Nhỏ hơn</option><option value="LTE">Nhỏ hơn hoặc bằng</option><option value="GT">Lớn hơn</option><option value="GTE">Lớn hơn hoặc bằng</option></select></Field><Field label={unit ? `Ngưỡng (${unit})` : "Ngưỡng"}><Input type="number" step="any" value={threshold} onChange={(event) => setConfig({ value: Number(event.target.value) })} /></Field><Field label="Duy trì (giây)"><Input type="number" min="0" step="1" value={numericValue(config.duration_seconds) ?? 0} onChange={(event) => setConfig({ duration_seconds: Number(event.target.value) })} /></Field></div>
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

function withUnit(value: unknown, unit: string | null): string {
  const text = String(value ?? "—")
  return unit && value !== undefined && value !== null && value !== "" ? `${text} ${unit}` : text
}

function conditionSummary(branch: ScenarioCatalogBranch, unit: string | null = null): string {
  const config = asRecord(branch.condition_config)
  if (branch.evaluator_type === "THRESHOLD") {
    const operator = typeof config.operator === "string" ? config.operator : "?"
    const symbols: Record<string, string> = { LT: "<", LTE: "≤", GT: ">", GTE: "≥", EQ: "=" }
    return `${symbols[operator] ?? operator} ${withUnit(config.value, unit)}`
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
      return `${String(row.severity ?? "")} ${String(row.operator ?? "")} ${row.value === undefined || row.value === null ? "" : withUnit(row.value, unit)}`.trim()
    }).join(" / ")
  }
  return branch.evaluator_type
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><Label>{label}</Label><div className="mt-1">{children}</div></div>
}
