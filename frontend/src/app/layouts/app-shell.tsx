import { useState } from "react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { ChevronDown, ChevronRight, Droplets, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, UserRound, X } from "lucide-react"
import { breadcrumbFromPath } from "@/app/navigation/breadcrumbs"
import { getNavigationItems } from "@/app/navigation/navigation-items"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Avatar, AvatarFallback } from "@/shared/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu"
import { useAuth } from "@/app/auth"
import { OwnerProfileDialog } from "@/widgets/owner-console/OwnerProfileDialog"
import { useTheme } from "@/app/providers/theme-provider"

const SIDEBAR_COLLAPSED_STORAGE_KEY = "aquaponics.sidebar.collapsed"

function readDesktopSidebarCollapsed() {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true"
  } catch {
    return false
  }
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(readDesktopSidebarCollapsed)
  const [profileOpen, setProfileOpen] = useState(false)
  const { session, logout, can, reload } = useAuth()
  const user = session?.user
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const items = getNavigationItems(can)
  const crumbs = breadcrumbFromPath(useLocation().pathname)

  const setDesktopSidebarCollapsed = (collapsed: boolean) => {
    setDesktopCollapsed(collapsed)
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(collapsed))
    } catch {
      // The layout still works when browser storage is unavailable.
    }
  }

  const renderSidebar = (collapsed: boolean) => <aside className={cn("flex h-full flex-col border-r border-primary-foreground/10 bg-primary text-primary-foreground transition-[width] duration-200", collapsed ? "w-20" : "w-72")} data-sidebar-collapsed={collapsed ? "true" : "false"}>
    <div className={cn("flex h-20 items-center border-b border-primary-foreground/10", collapsed ? "justify-center px-2" : "gap-3 px-6")}><div className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-foreground text-primary"><Droplets className="size-5" /></div>{!collapsed ? <div className="min-w-0"><div className="font-bold tracking-tight">Aquaponics</div><div className="text-xs text-primary-foreground/65">Trạm quan trắc</div></div> : null}</div>
    <nav className={cn("flex flex-1 flex-col gap-1 overflow-y-auto", collapsed ? "p-2" : "p-4")}>{items.map(({ label, path, icon: Icon }) => <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} aria-label={collapsed ? label : undefined} title={collapsed ? label : undefined} className={({ isActive }) => cn("flex items-center rounded-lg py-2.5 text-sm font-medium transition-colors", collapsed ? "justify-center px-2" : "gap-3 px-3", isActive ? "bg-primary-foreground text-primary shadow-sm" : "text-primary-foreground/75 hover:bg-primary-foreground/10 hover:text-primary-foreground")}><Icon className="size-4 shrink-0" />{!collapsed ? <span>{label}</span> : null}</NavLink>)}</nav>
  </aside>

  return <div className="min-h-screen bg-background"><div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{renderSidebar(desktopCollapsed)}</div>{mobileOpen && <div className="fixed inset-0 z-50 lg:hidden"><button className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} aria-label="Đóng menu" /><div className="relative h-full w-72">{renderSidebar(false)}<Button variant="ghost" size="icon" className="absolute right-2 top-2" onClick={() => setMobileOpen(false)} aria-label="Đóng menu"><X /></Button></div></div>}
    <div className={cn("transition-[padding] duration-200", desktopCollapsed ? "lg:pl-20" : "lg:pl-72")}><header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b bg-background/85 px-4 backdrop-blur-xl sm:px-6"><div className="flex min-w-0 items-center gap-2"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Mở menu"><Menu /></Button><Button variant="ghost" size="icon" className="hidden lg:inline-flex" onClick={() => setDesktopSidebarCollapsed(!desktopCollapsed)} aria-label={desktopCollapsed ? "Mở rộng thanh bên" : "Thu nhỏ thanh bên"} title={desktopCollapsed ? "Mở rộng thanh bên" : "Thu nhỏ thanh bên"} aria-pressed={desktopCollapsed}>{desktopCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}</Button><nav aria-label="Đường dẫn" className="hidden min-w-0 items-center gap-1.5 text-sm sm:flex">{crumbs.map((crumb, index) => <span key={crumb} className="flex min-w-0 items-center gap-1.5">{index > 0 ? <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/60" aria-hidden="true" /> : null}<span className={cn("truncate", index === crumbs.length - 1 ? "font-medium text-foreground" : "text-muted-foreground")}>{crumb}</span></span>)}</nav></div><div className="ml-auto flex items-center gap-2"><Button variant="ghost" size="icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Đổi giao diện">{theme === "dark" ? <Sun /> : <Moon />}</Button><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" aria-label="Menu tài khoản" className="group h-10 gap-2 px-2 data-[state=open]:bg-accent"><Avatar><AvatarFallback>{user?.full_name?.slice(0, 2).toUpperCase()}</AvatarFallback></Avatar><span className="hidden max-w-36 truncate text-left sm:block">{user?.full_name}</span><ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" alignOffset={0} sideOffset={8} collisionPadding={8} className="w-56 rounded-xl p-1.5"><DropdownMenuLabel><div className="font-medium">{user?.full_name}</div><div className="truncate text-xs font-normal text-muted-foreground">{user?.email}</div></DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem onSelect={() => setProfileOpen(true)}><UserRound /> Hồ sơ cá nhân</DropdownMenuItem><DropdownMenuItem onSelect={() => { void logout().finally(() => navigate("/login")) }}><LogOut /> Đăng xuất</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></header><main className="mx-auto max-w-[1600px] p-4 sm:p-6 lg:p-8"><Outlet /></main></div>
    <OwnerProfileDialog
      open={profileOpen}
      onOpenChange={setProfileOpen}
      user={session?.user}
      onSaved={reload}
      onPasswordChanged={() => { setProfileOpen(false); void logout().finally(() => navigate("/login?password=changed", { replace: true })) }}
    />
  </div>
}
