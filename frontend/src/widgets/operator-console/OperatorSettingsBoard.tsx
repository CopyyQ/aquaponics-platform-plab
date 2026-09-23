import { BellRing } from "lucide-react"
import type { AlertDeliveryRecipient, AquaponicsSystem } from "@/api/contracts"
import { recipientStatusLabel } from "./operator-console.model"
import { Card } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"

export function OperatorSettingsBoard({
  system,
  recipients,
  telegramEnabled,
}: {
  system: AquaponicsSystem
  recipients: AlertDeliveryRecipient[]
  telegramEnabled: boolean
}) {
  const rows = [
    { label: "Tên hệ thống", value: system.name },
    { label: "Vị trí", value: system.location || "Chưa đặt vị trí" },
    { label: "Mã hệ thống", value: system.code },
  ]
  return (
    <div className="space-y-5">
      <Card className="rounded-2xl border-0 p-6 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
        <h2 className="mb-4 text-base font-semibold text-slate-800">Thông tin hệ thống</h2>
        <dl className="divide-y divide-slate-100">
          {rows.map((row) => (
            <div className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0" key={row.label}>
              <dt className="text-sm text-slate-500">{row.label}</dt>
              <dd className="text-sm font-medium text-slate-800">{row.value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card className="rounded-2xl border-0 p-6 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
        <h2 className="mb-4 text-base font-semibold text-slate-800">Người nhận thông báo Telegram</h2>
        {recipients.length ? (
          <ul className="divide-y divide-slate-100">
            {recipients.map((recipient) => {
              const on = recipientStatusLabel(recipient, telegramEnabled) === "Đang bật"
              return (
                <li className="flex items-center justify-between gap-3 py-4 first:pt-0 last:pb-0" key={recipient.id}>
                  <div>
                    <p className="font-medium text-slate-800">{recipient.name}</p>
                    <p className="text-sm text-slate-400">Nhận khi có cảnh báo mới</p>
                  </div>
                  <span className={on ? "text-sm font-medium text-emerald-600" : "text-sm font-medium text-slate-400"}>{on ? "Đang bật" : "Đã tắt"}</span>
                </li>
              )
            })}
          </ul>
        ) : (
          <EmptyState icon={BellRing} title="Chưa có người nhận Telegram" description="Quản trị viên chưa cấu hình Telegram Chat ID cho hệ thống này." />
        )}
      </Card>
    </div>
  )
}

export function OperatorSettingsSkeleton() {
  return <div className="space-y-4"><Skeleton className="h-56" /><Skeleton className="h-64" /></div>
}
