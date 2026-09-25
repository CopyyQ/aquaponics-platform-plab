import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ExternalLink, KeyRound, LogOut, Plus, Settings, UserRound } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import {
  createUserAquaponicsSystem, forceLogoutUser, getUser, listDeviceTemplates, listRoles,
  listScenarioCatalogs, listUserAquaponicsSystems, queryKeys, setManagedUserPassword,
  updateManagedUser, userLifecycle,
} from "@/api/resources"
import type { UserStatus } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { Avatar, AvatarFallback } from "@/shared/ui/avatar"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/shared/ui/alert-dialog"
import { EmptyState } from "@/shared/ui/empty-state"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"
import { toast } from "sonner"

// Hieu ung chi ap dung cho cac hop thoai quan ly tai khoan o man hinh nay.
const accountDialogMotion = "duration-200 ease-out data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 motion-reduce:animate-none"
const accountOverlayMotion = "duration-200 data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 motion-reduce:animate-none"

type LifecycleAction = "activate" | "disable" | "lock" | "unlock" | "restore" | "soft-delete"
type Confirmation = { action: LifecycleAction; title: string } | null

export function UserDetailPage() {
  return <UserDetailView userId={useParams().userId ?? ""} />
}

// Dung cho ca route /users/:id lan modal trong danh sach nguoi dung.
export function UserDetailView({ userId, embedded = false }: { userId: string; embedded?: boolean }) {
  const validId = Boolean(userId)
  const { can, session } = useAuth()
  const client = useQueryClient()
  const [manageOpen, setManageOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [confirmation, setConfirmation] = useState<Confirmation>(null)
  const [reason, setReason] = useState("")
  const user = useQuery({ queryKey: queryKeys.user(userId), queryFn: () => getUser(userId), enabled: validId })
  const roles = useQuery({ queryKey: queryKeys.roles, queryFn: listRoles, enabled: validId && can("users.update") })
  const refreshUser = async () => { await Promise.all([client.invalidateQueries({ queryKey: queryKeys.user(userId) }), client.invalidateQueries({ queryKey: queryKeys.users })]) }
  const lifecycle = useMutation({ mutationFn: ({ action, reason: why }: { action: LifecycleAction; reason?: string }) => userLifecycle(userId, action, { reason: why }), onSuccess: async (value) => { await refreshUser(); setConfirmation(null); setReason(""); toast.success(value.message) }, onError: (error) => toast.error(errorMessage(error)) })
  const forceLogout = useMutation({ mutationFn: () => forceLogoutUser(userId), onSuccess: (value) => toast.success(value.message), onError: (error) => toast.error(errorMessage(error)) })
  const confirm = (action: LifecycleAction, title: string) => { setManageOpen(false); setConfirmation({ action, title }) }
  if (!validId) return <EmptyState icon={UserRound} title="Đường dẫn người dùng không hợp lệ" description="Mã người dùng phải là số nguyên dương." />
  if (user.isLoading) return <div className="space-y-5"><Skeleton className="h-20" /><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
  if (user.isError || !user.data) return <EmptyState icon={UserRound} title="Không thể tải người dùng" description={errorMessage(user.error)} />
  const value = user.data
  const isSelf = session?.user.id === value.id
  return <div className={embedded ? "space-y-5" : "mx-auto max-w-5xl space-y-5"}>
    {embedded ? null : <Link className="inline-flex items-center gap-2 text-sm text-primary hover:underline" to="/users"><ArrowLeft className="size-4" />Danh sách người dùng</Link>}
    <h1 className="text-balance pr-8 text-3xl font-bold">Thông tin tài khoản</h1>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,35fr)_minmax(0,65fr)]">
      <Card className="h-full"><CardContent className="flex h-full flex-col items-center gap-4 p-6 text-center">
        <Avatar className="size-20"><AvatarFallback className="text-xl">{initialsOf(value.full_name)}</AvatarFallback></Avatar>
        <div className="min-w-0 space-y-1"><p className="text-balance text-lg font-semibold">{value.full_name}</p><p className="truncate text-sm text-muted-foreground">@{value.username}</p></div>
        <StatusBadge value={value.status} />
        <div className="flex w-full flex-col items-stretch gap-1.5 border-t pt-4 text-center"><Label>Vai trò</Label>{can("users.update") ? <Select value={value.role_id ? String(value.role_id) : "none"} onValueChange={(next) => { void updateManagedUser(userId, { role_id: next === "none" ? null : Number(next) }).then(refreshUser).catch((e: unknown) => toast.error(errorMessage(e))) }}><SelectTrigger className="w-full gap-2"><SelectValue /></SelectTrigger><SelectContent position="popper" sideOffset={6} className="w-auto min-w-[var(--radix-select-trigger-width)] whitespace-nowrap"><SelectItem value="none">Chưa gán</SelectItem>{(roles.data ?? []).map((role) => <SelectItem value={String(role.id)} key={role.id}>{role.name} ({role.code})</SelectItem>)}</SelectContent></Select> : <p className="font-medium">{value.role_name ?? value.role_code ?? "Chưa gán"}</p>}</div>
        {can("users.update") || can("users.set_password") ? <Button className="mt-auto w-full" variant="outline" onClick={() => setManageOpen(true)}><Settings />Quản lý tài khoản</Button> : null}
      </CardContent></Card>
      <div className="space-y-5">
        <Card><CardHeader><CardTitle>Thông tin chi tiết</CardTitle></CardHeader><CardContent className="grid gap-5 sm:grid-cols-2">
          <Field label="Email" value={value.email} /><Field label="Số điện thoại" value={value.phone_number || "Chưa cấu hình"} />
          <Field label="Ngày tạo" value={formatDate(value.created_at)} /><Field label="Lần đăng nhập cuối" value={formatDate(value.last_login_at)} />
        </CardContent></Card>
        <UserAquaponicsSystems userId={userId} canManage={can("aquaponics_systems.manage_all")} />
      </div>
    </div>
    <ManageAccountDialog open={manageOpen} onOpenChange={setManageOpen} status={value.status} isSelf={isSelf} can={can} onPassword={() => { setManageOpen(false); setPasswordOpen(true) }} onForceLogout={() => forceLogout.mutate()} onConfirm={confirm} pending={forceLogout.isPending} />
    <PasswordDialog userId={userId} open={passwordOpen} onOpenChange={setPasswordOpen} />
    <AlertDialog open={Boolean(confirmation)} onOpenChange={(open) => { if (!open) { setConfirmation(null); setReason("") } }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{confirmation?.title}</AlertDialogTitle><AlertDialogDescription>Thao tác sẽ thay đổi quyền truy cập của tài khoản. Hãy nhập lý do để lưu cùng lịch sử quản trị.</AlertDialogDescription></AlertDialogHeader><div><Label htmlFor="lifecycle-reason">Lý do</Label><Input id="lifecycle-reason" className="mt-1" value={reason} onChange={(event) => setReason(event.target.value)} /></div><AlertDialogFooter><AlertDialogCancel>Hủy</AlertDialogCancel><AlertDialogAction variant={confirmation?.action === "soft-delete" ? "destructive" : "default"} disabled={lifecycle.isPending || reason.trim().length < 3} onClick={(event) => { event.preventDefault(); if (confirmation) lifecycle.mutate({ action: confirmation.action, reason: reason.trim() }) }}>Xác nhận</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>
}

function UserAquaponicsSystems({ userId, canManage }: { userId: string; canManage: boolean }) {
  const client = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [templateId, setTemplateId] = useState(0)
  const [scenarioCatalogId, setScenarioCatalogId] = useState(0)
  const systems = useQuery({ queryKey: queryKeys.userSystems(userId), queryFn: () => listUserAquaponicsSystems(userId) })
  const templates = useQuery({ queryKey: queryKeys.templates, queryFn: listDeviceTemplates, enabled: createOpen })
  const scenarios = useQuery({ queryKey: queryKeys.scenarioCatalogsByTemplate(templateId), queryFn: () => listScenarioCatalogs(templateId), enabled: createOpen && templateId > 0 })
  const availableScenarios = useMemo(() => (scenarios.data ?? []).filter((scenario) => scenario.device_template_id === templateId && scenario.is_active), [scenarios.data, templateId])
  useEffect(() => {
    if (!createOpen) return
    if (!templateId) {
      setTemplateId(templates.data?.find((item) => item.is_active)?.id ?? 0)
      setScenarioCatalogId(0)
      return
    }
    if (!availableScenarios.some((scenario) => scenario.id === scenarioCatalogId)) {
      setScenarioCatalogId(availableScenarios[0]?.id ?? 0)
    }
  }, [availableScenarios, createOpen, scenarioCatalogId, templateId, templates.data])
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: queryKeys.userSystems(userId) }), client.invalidateQueries({ queryKey: queryKeys.systems })]) }
  const creation = useMutation({ mutationFn: () => createUserAquaponicsSystem(userId, { device_template_id: templateId, scenario_catalog_id: scenarioCatalogId }), onSuccess: async () => { await refresh(); setCreateOpen(false); toast.success("Đã tạo Hệ thống Aquaponics") }, onError: (error) => toast.error(errorMessage(error)) })
  return <Card><CardHeader className="flex-row items-center justify-between gap-3"><div><CardTitle className="text-balance">Hệ thống Aquaponics sở hữu</CardTitle><p className="mt-1 text-sm text-muted-foreground">Mỗi người dùng chỉ được sở hữu một dự án.</p></div>{canManage && !systems.data?.length ? <Button onClick={() => setCreateOpen(true)}><Plus />Tạo Hệ thống Aquaponics</Button> : null}</CardHeader><CardContent>
    {systems.isLoading ? <Skeleton className="h-36" /> : systems.isError ? <EmptyState icon={UserRound} title="Không thể tải Hệ thống Aquaponics" description={errorMessage(systems.error)} /> : systems.data?.length ? <div className="grid gap-3">{systems.data.map((system) => <article key={system.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/40 p-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="text-pretty font-semibold">{system.name}</h3><StatusBadge value={system.status} /></div><p className="mt-1 text-sm text-muted-foreground">Mã hệ thống <span className="font-mono">{system.code}</span> · Chủ hệ thống</p></div><Button asChild size="sm" variant="outline"><Link to={`/aquaponics-systems/${system.id}`}><ExternalLink />Xem hệ thống</Link></Button></article>)}</div> : <EmptyState icon={UserRound} title="Chưa sở hữu Hệ thống Aquaponics" description="Tạo Hệ thống Aquaponics đầu tiên cho tài khoản này." />}
    <Dialog open={createOpen} onOpenChange={setCreateOpen}><DialogContent><DialogHeader><DialogTitle>Tạo Hệ thống Aquaponics</DialogTitle><DialogDescription>Tên dự án được cố định là “Hệ thống Aquaponics”. Chọn thiết bị trước, sau đó chọn một kịch bản thuộc chính thiết bị đó.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); creation.mutate() }}><div><Label htmlFor="owned-system-name">Tên hệ thống</Label><Input id="owned-system-name" className="mt-1" value="Hệ thống Aquaponics" disabled /></div><div><Label>Mẫu thiết bị</Label><Select value={templateId ? String(templateId) : ""} onValueChange={(value) => { setTemplateId(Number(value)); setScenarioCatalogId(0) }}><SelectTrigger className="mt-1"><SelectValue placeholder="Chọn mẫu thiết bị" /></SelectTrigger><SelectContent>{(templates.data ?? []).filter((item) => item.is_active).map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.name} · {item.sensors.length} cảm biến · {item.actuators.length} cơ cấu</SelectItem>)}</SelectContent></Select></div><div><Label>Kịch bản của thiết bị</Label><Select value={scenarioCatalogId ? String(scenarioCatalogId) : ""} onValueChange={(value) => setScenarioCatalogId(Number(value))} disabled={!templateId || scenarios.isLoading}><SelectTrigger className="mt-1"><SelectValue placeholder={templateId ? "Chọn kịch bản của thiết bị" : "Chọn thiết bị trước"} /></SelectTrigger><SelectContent>{availableScenarios.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.name} · {item.items.filter((resource) => resource.target_type === "SENSOR").length} cảm biến · {item.items.filter((resource) => resource.target_type === "ACTUATOR").length} cơ cấu</SelectItem>)}</SelectContent></Select>{templateId && !scenarios.isLoading && !availableScenarios.length ? <p className="mt-1 text-xs text-destructive">Thiết bị này chưa có kịch bản hoạt động. Hãy tạo kịch bản trong Danh mục trước.</p> : null}</div>{creation.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(creation.error)}</p> : null}<DialogFooter><Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>Hủy</Button><Button type="submit" disabled={!templateId || !scenarioCatalogId || creation.isPending}>Tạo hệ thống</Button></DialogFooter></form></DialogContent></Dialog>
  </CardContent></Card>
}

function ManageAccountDialog({ open, onOpenChange, status, isSelf, can, onPassword, onForceLogout, onConfirm, pending }: { open: boolean; onOpenChange: (open: boolean) => void; status: UserStatus; isSelf: boolean; can: (permission: string) => boolean; onPassword: () => void; onForceLogout: () => void; onConfirm: (action: LifecycleAction, title: string) => void; pending: boolean }) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className={accountDialogMotion} overlayClassName={accountOverlayMotion}><DialogHeader><DialogTitle>Quản lý tài khoản</DialogTitle><DialogDescription></DialogDescription></DialogHeader><div className="grid gap-2 sm:grid-cols-2">{can("users.set_password") ? <Button variant="outline" onClick={onPassword}><KeyRound />Đặt mật khẩu</Button> : null}{can("users.force_logout") ? <Button variant="outline" onClick={onForceLogout} disabled={pending}><LogOut />Thu hồi phiên đăng nhập</Button> : null}{status === "ACTIVE" && can("users.lock") && !isSelf ? <Button variant="outline" onClick={() => onConfirm("lock", "Khóa tài khoản?")}>Khóa</Button> : null}{status === "LOCKED" && can("users.unlock") ? <Button onClick={() => onConfirm("unlock", "Mở khóa tài khoản?")}>Mở khóa</Button> : null}{status === "ACTIVE" && can("users.update") && !isSelf ? <Button variant="outline" onClick={() => onConfirm("disable", "Vô hiệu hóa tài khoản?")}>Vô hiệu hóa</Button> : null}{status === "DISABLED" && can("users.update") ? <Button onClick={() => onConfirm("activate", "Kích hoạt tài khoản?")}>Kích hoạt</Button> : null}{status !== "SOFT_DELETED" && can("users.delete") && !isSelf ? <Button variant="destructive" onClick={() => onConfirm("soft-delete", "Xóa mềm tài khoản?")}>Xóa mềm</Button> : null}{status === "SOFT_DELETED" && can("users.update") ? <Button onClick={() => onConfirm("restore", "Khôi phục tài khoản?")}>Khôi phục</Button> : null}</div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Đóng</Button></DialogFooter></DialogContent></Dialog>
}

function PasswordDialog({ userId, open, onOpenChange }: { userId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const mutation = useMutation({ mutationFn: () => setManagedUserPassword(userId, { new_password: password, confirm_password: confirm, invalidate_sessions: true, must_change_password: true }), onSuccess: (value) => { toast.success(value.message); onOpenChange(false); setPassword(""); setConfirm("") }, onError: (error) => toast.error(errorMessage(error)) })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className={accountDialogMotion} overlayClassName={accountOverlayMotion}><DialogHeader><DialogTitle>Đặt mật khẩu</DialogTitle><DialogDescription>Người dùng sẽ phải đổi mật khẩu sau lần đăng nhập kế tiếp.</DialogDescription></DialogHeader><div className="space-y-3"><div><Label htmlFor="managed-password">Mật khẩu mới</Label><Input id="managed-password" className="mt-1" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></div><div><Label htmlFor="managed-confirm">Xác nhận mật khẩu</Label><Input id="managed-confirm" className="mt-1" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} /></div></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Hủy</Button><Button disabled={password.length < 8 || password !== confirm || mutation.isPending} onClick={() => mutation.mutate()}>Lưu mật khẩu</Button></DialogFooter></DialogContent></Dialog>
}

function initialsOf(fullName: string) { return fullName.split(" ").filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase() || "ND" }
function Field({ label, value }: { label: string; value: string }) { return <div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-1 font-medium tabular-nums">{value}</p></div> }
function formatDate(value: string | null) { return value ? new Date(value).toLocaleString("vi-VN") : "Chưa có" }
