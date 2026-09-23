import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Bell, Droplets, LayoutDashboard, LogOut, Menu, Settings, UserRound, Wrench, X } from "lucide-react"
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom"
import { getMonitoringLatest, getSystem, listAlerts, listSystems, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { accountRoleLabel, isOperatorConsole, readAccountRole } from "@/app/lib/operator-console"
import { collectActuatorRows, collectSensorCards, formatHeaderDate, isOpenAlert, pageTitleFromPath } from "@/widgets/operator-console/operator-console.model"
import { OperatorAlertBell } from "@/widgets/operator-console/OperatorAlertBell"
import { cn } from "@/shared/lib/utils"
import { Avatar, AvatarFallback } from "@/shared/ui/avatar"
import { Button } from "@/shared/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu"
import { Skeleton } from "@/shared/ui/skeleton"

export function OperatorConsoleLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { session, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const params = useParams()
  const role = readAccountRole()
  const locked = Boolean(session?.user.must_change_password)
  const sidebarRole = isOperatorConsole(session?.permissions, role) && role !== "VIEWER" && role !== "TECHNICIAN"
    ? "Chủ hệ thống"
    : accountRoleLabel(role)
  const systems = useQuery({ queryKey: queryKeys.systems, queryFn: listSystems })
  const systemId = params.systemId ?? (systems.data?.length === 1 ? systems.data[0].id : "")
  const system = useQuery({ queryKey: queryKeys.system(systemId), queryFn: () => getSystem(systemId), enabled: Boolean(systemId) })
  const latest = useQuery({
    queryKey: queryKeys.monitoringLatest(systemId),
    queryFn: () => getMonitoringLatest(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })

  const sensorCount = collectSensorCards(latest.data).length
  const actuatorCount = collectActuatorRows(latest.data).length
  const openAlertCount = (alerts.data ?? []).filter(isOpenAlert).length

  const base = systemId ? `/aquaponics-systems/${systemId}` : "/aquaponics-systems"
  const items = [
    { label: "Tổng quan", path: `${base}/overview`, icon: LayoutDashboard, badge: null as string | null },
    { label: "Thiết bị", path: `${base}/devices`, icon: Wrench, badge: sensorCount || actuatorCount ? `${actuatorCount} · ${sensorCount}` : null },
    { label: "Cảnh báo", path: `${base}/alerts`, icon: Bell, badge: openAlertCount ? String(openAlertCount) : null, alert: true },
    { label: "Cài đặt", path: `${base}/settings`, icon: Settings, badge: null },
  ]
  const initials = (session?.user.full_name ?? "ND").split(" ").filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase()
  const title = pageTitleFromPath(location.pathname)
  const subtitle = system.data
    ? [system.data.code, system.data.location, formatHeaderDate()].filter(Boolean).join(" · ")
    : formatHeaderDate()

  const sidebar = (
    <aside className="flex h-full w-64 flex-col bg-[#0d5c4d] text-white">
      <div className="flex items-center gap-3 px-5 py-6">
        <div className="grid size-11 place-items-center rounded-2xl bg-white text-[#0d5c4d]"><Droplets className="size-5" aria-hidden="true" /></div>
        <div className="min-w-0">
          <div className="text-lg font-bold tracking-tight">AquaMonitor</div>
          <div className="truncate text-xs text-white/65">{system.data?.name ?? "Hệ thống Aquaponics"}</div>
        </div>
      </div>
      {systems.data && systems.data.length > 1 ? (
        <div className="px-4 pb-3">
          <label className="sr-only" htmlFor="operator-system-switcher">Chọn hệ thống</label>
          <select
            id="operator-system-switcher"
            className="h-10 w-full rounded-xl border-0 bg-white/10 px-3 text-sm text-white outline-none"
            value={systemId}
            onChange={(event) => navigate(`/aquaponics-systems/${event.target.value}/overview`)}
          >
            <option value="" className="text-slate-900">Chọn hệ thống</option>
            {systems.data.map((item) => <option className="text-slate-900" key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
      ) : null}
      <nav className="flex flex-1 flex-col gap-1 px-3">
        {items.map(({ label, path, icon: Icon, badge, alert }) => (
          <NavLink
            key={path}
            to={path}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) => cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors", isActive ? "bg-white/15 text-white" : "text-white/75 hover:bg-white/10 hover:text-white")}
          >
            <Icon className="size-4" aria-hidden="true" />
            <span className="flex-1">{label}</span>
            {badge ? <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", alert ? "bg-red-500 text-white" : "bg-white/15 text-white")}>{badge}</span> : null}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto p-4">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="flex w-full items-center gap-3 rounded-2xl px-1 py-1 text-left hover:bg-white/10">
              <Avatar className="size-10 bg-white/15 text-white"><AvatarFallback className="bg-transparent text-white">{initials}</AvatarFallback></Avatar>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{session?.user.full_name}</span>
                <span className="block truncate text-xs text-white/60">{sidebarRole}</span>
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel>
              <div className="font-medium">{session?.user.full_name}</div>
              <div className="truncate text-xs font-normal text-muted-foreground">{session?.user.email}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/profile")}><UserRound /> Hồ sơ cá nhân</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => { void logout().finally(() => navigate("/login")) }}><LogOut /> Đăng xuất</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  )

  return (
    <div className="min-h-screen bg-[#f3f6f4]">
      <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{sidebar}</div>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} aria-label="Đóng menu" />
          <div className="relative h-full w-64">{sidebar}<Button variant="ghost" size="icon" className="absolute right-2 top-2 text-white" onClick={() => setMobileOpen(false)}><X /></Button></div>
        </div>
      ) : null}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 bg-[#f3f6f4] px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Mở menu"><Menu /></Button>
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-semibold text-slate-800">{title}</h1>
              <p className="truncate text-sm text-slate-400">{subtitle}</p>
            </div>
          </div>
          <OperatorAlertBell
            alerts={alerts.data}
            alertsHref={systemId ? `${base}/alerts` : "/aquaponics-systems"}
            openCount={openAlertCount}
            isLoading={alerts.isLoading}
          />
        </header>
        <main className="px-4 pb-8 sm:px-6 lg:px-8">
          {locked ? (
            <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Bạn nên đổi mật khẩu sớm. <Link className="font-semibold underline" to="/profile?change-password=required">Mở hồ sơ</Link> — vẫn có thể xem Tổng quan, Thiết bị, Cảnh báo và Cài đặt.
            </div>
          ) : null}
          {systems.isLoading ? <Skeleton className="h-72" /> : <Outlet />}
        </main>
      </div>
    </div>
  )
}

export function OperatorSystemFrame() {
  const systemId = useParams().systemId ?? ""
  const system = useQuery({ queryKey: queryKeys.system(systemId), queryFn: () => getSystem(systemId), enabled: Boolean(systemId) })
  if (system.isLoading) return <Skeleton className="h-72" />
  if (system.isError || !system.data) {
    return <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700">{errorMessage(system.error) || "Không thể tải hệ thống Aquaponics."}</div>
  }
  return <Outlet context={{ system: system.data }} />
}
