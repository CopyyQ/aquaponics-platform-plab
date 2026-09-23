import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Droplets, LogOut, UserRound } from "lucide-react"
import { Link, Outlet, useNavigate, useParams } from "react-router-dom"
import { getSystem, listSystems, queryKeys } from "@/api/resources"
import { useAuth } from "@/app/auth"
import { OwnerProfileDialog } from "@/widgets/owner-console/OwnerProfileDialog"
import { Avatar, AvatarFallback } from "@/shared/ui/avatar"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu"
import { Skeleton } from "@/shared/ui/skeleton"

// Layout riêng cho role OWNER: header ngang full-width, không sidebar.
export function OwnerConsoleLayout() {
  const { session, reload, logout } = useAuth()
  const navigate = useNavigate()
  const params = useParams()
  const [profileOpen, setProfileOpen] = useState(false)
  const locked = Boolean(session?.user.must_change_password)
  const systems = useQuery({ queryKey: queryKeys.systems, queryFn: listSystems })
  const systemId = params.systemId ?? (systems.data?.length === 1 ? systems.data[0].id : "")
  const system = useQuery({ queryKey: queryKeys.system(systemId), queryFn: () => getSystem(systemId), enabled: Boolean(systemId) })
  const initials = (session?.user.full_name ?? "ND").split(" ").filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase()
  const overviewPath = systemId ? `/aquaponics-systems/${systemId}/overview` : "/aquaponics-systems"

  return (
    <div className="min-h-screen bg-[#f3f6f4]">
      <header className="sticky top-0 z-30 bg-[#0d5c4d] text-white shadow-md">
        <div className="flex items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <Link to={overviewPath} className="flex min-w-0 items-center gap-3 rounded-xl hover:bg-white/10 transition-colors">
              <div className="grid size-10 place-items-center rounded-xl bg-white text-[#0d5c4d] shrink-0"><Droplets className="size-5" aria-hidden="true" /></div>
              <div className="min-w-0">
                <div className="text-base font-bold tracking-tight truncate">AquaMonitor</div>
                <div className="text-xs text-white/70 truncate">{system.data?.name ?? "Hệ thống Aquaponics"}</div>
              </div>
            </Link>
            {systems.data && systems.data.length > 1 ? (
              <select
                className="ml-4 h-9 rounded-lg border-0 bg-white/15 px-3 text-sm text-white outline-none"
                value={systemId}
                onChange={(event) => navigate(`/aquaponics-systems/${event.target.value}/overview`)}
              >
                <option value="" className="text-slate-900">Chọn hệ thống</option>
                {systems.data.map((item) => <option key={item.id} value={item.id} className="text-slate-900">{item.name}</option>)}
              </select>
            ) : null}
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                {/* Trigger: avatar (nhận diện) + tên người đang đăng nhập + chevron (báo có menu) */}
                <button
                  type="button"
                  aria-label="Menu tài khoản"
                  className="group flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 data-[state=open]:bg-white/15"
                >
                  <Avatar className="size-9 bg-white/20 text-white"><AvatarFallback className="bg-transparent text-white text-sm font-semibold">{initials}</AvatarFallback></Avatar>
                  <span className="hidden max-w-40 truncate text-sm font-medium text-white sm:block">{session?.user.full_name}</span>
                  <ChevronDown className="size-4 shrink-0 text-white/70 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" alignOffset={0} sideOffset={8} collisionPadding={8} className="w-56 rounded-xl p-1.5">
                <DropdownMenuLabel>
                  <div className="font-medium">{session?.user.full_name}</div>
                  <div className="truncate text-xs font-normal text-muted-foreground">{session?.user.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="rounded-lg" onSelect={() => setProfileOpen(true)}><UserRound className="size-4" /> Hồ sơ cá nhân</DropdownMenuItem>
                <DropdownMenuItem
                  className="rounded-lg text-rose-600 focus:bg-rose-50 focus:text-rose-700"
                  onSelect={() => { void logout().finally(() => navigate("/login")) }}
                >
                  <LogOut className="size-4" /> Đăng xuất
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <OwnerProfileDialog
        open={profileOpen}
        onOpenChange={setProfileOpen}
        user={session?.user}
        onSaved={reload}
        onPasswordChanged={() => { setProfileOpen(false); void logout().finally(() => navigate("/login?password=changed", { replace: true })) }}
      />

      <main className="px-6 py-5">
        {locked ? (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
            Bạn nên đổi mật khẩu sớm. <Link className="font-semibold underline" to="/profile?change-password=required">Mở hồ sơ</Link>
          </div>
        ) : null}
        {systems.isLoading ? <Skeleton className="h-72" /> : <Outlet />}
      </main>
    </div>
  )
}
