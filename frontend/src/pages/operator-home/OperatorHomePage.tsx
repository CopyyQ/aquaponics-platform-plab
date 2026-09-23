import { useQuery } from "@tanstack/react-query"
import { Droplets } from "lucide-react"
import { Link, Navigate } from "react-router-dom"
import { listSystems, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { Card, CardContent } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"

export function OperatorHomePage() {
  const systems = useQuery({ queryKey: queryKeys.systems, queryFn: listSystems })
  if (systems.isLoading) return <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-36" /><Skeleton className="h-36" /></div>
  if (systems.isError) return <EmptyState icon={Droplets} title="Không thể tải hệ thống" description={errorMessage(systems.error)} />
  const items = systems.data ?? []
  if (items.length === 1) return <Navigate to={`/aquaponics-systems/${items[0].id}/overview`} replace />
  if (!items.length) {
    return <EmptyState icon={Droplets} title="Chưa có hệ thống" description="Tài khoản của bạn chưa được gán hệ thống Aquaponics." />
  }
  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">Hệ thống của bạn</h1>
        <p className="text-sm text-slate-500">Chọn một hệ thống để xem tổng quan vận hành.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((system) => (
          <Link key={system.id} to={`/aquaponics-systems/${system.id}/overview`}>
            <Card className="h-full rounded-2xl border-0 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)] transition-transform hover:-translate-y-0.5">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="font-semibold text-slate-800">{system.name}</h2>
                  <StatusBadge value={system.status} />
                </div>
                <p className="mt-2 text-sm text-slate-500">{system.code}</p>
                <p className="mt-4 text-sm text-slate-600">{system.location || "Chưa đặt vị trí"}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </section>
  )
}
