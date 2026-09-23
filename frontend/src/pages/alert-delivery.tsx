import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BellRing, Bot, Pencil, Plus, Send, ShieldCheck, Trash2 } from "lucide-react"
import { useParams } from "react-router-dom"
import { toast } from "sonner"

import { errorMessage } from "@/api/client"
import {
  addAlertDeliveryRecipient,
  deleteAlertDeliveryRecipient,
  getAlertDeliveryHistory,
  getAlertDeliverySettings,
  queryKeys,
  testAlertDeliveryRecipient,
  updateAlertDeliveryRecipient,
  updateAlertDeliverySettings,
} from "@/api/resources"
import type {
  AlertDeliveryHistoryItem,
  AlertDeliveryRecipient,
  AlertDeliverySettings,
} from "@/api/contracts"
import { useAuth } from "@/app/auth"
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import { EmptyState } from "@/shared/ui/empty-state"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Skeleton } from "@/shared/ui/skeleton"
import { StatusBadge } from "@/shared/ui/status-badge"
import { Switch } from "@/shared/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

export function AlertDeliveryPage() {
  const systemId = useParams().systemId ?? ""
  const client = useQueryClient()
  const { can } = useAuth()
  const [editing, setEditing] = useState<AlertDeliveryRecipient | "new" | null>(null)
  const [deleting, setDeleting] = useState<AlertDeliveryRecipient | null>(null)

  const settings = useQuery({
    queryKey: queryKeys.deliverySettings(systemId),
    queryFn: () => getAlertDeliverySettings(systemId),
    enabled: Boolean(systemId) && can("notifications.settings.read"),
  })
  const history = useQuery({
    queryKey: queryKeys.deliveryHistory(systemId),
    queryFn: () => getAlertDeliveryHistory(systemId),
    enabled: Boolean(systemId) && can("notifications.history.read"),
  })

  const save = useMutation({
    mutationFn: (next: Pick<AlertDeliverySettings, "telegram_enabled" | "notify_alert_recovered">) =>
      updateAlertDeliverySettings(systemId, next),
    onSuccess: async (data) => {
      client.setQueryData(queryKeys.deliverySettings(systemId), data)
      await client.invalidateQueries({ queryKey: queryKeys.deliveryHistory(systemId) })
      toast.success("Đã lưu cấu hình Telegram")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.deliverySettings(systemId) }),
      client.invalidateQueries({ queryKey: queryKeys.deliveryHistory(systemId) }),
    ])
  }

  if (!can("notifications.settings.read")) {
    return <EmptyState icon={BellRing} title="Không có quyền xem Telegram" description="Tài khoản hiện tại không có quyền xem cấu hình thông báo." />
  }
  if (settings.isLoading) return <Skeleton className="h-[28rem]" />
  if (settings.isError || !settings.data) {
    return <EmptyState icon={BellRing} title="Không thể tải cấu hình Telegram" description={errorMessage(settings.error)} />
  }

  const data = settings.data
  const patch = (value: Partial<Pick<AlertDeliverySettings, "telegram_enabled" | "notify_alert_recovered">>) => {
    save.mutate({
      telegram_enabled: value.telegram_enabled ?? data.telegram_enabled,
      notify_alert_recovered: value.notify_alert_recovered ?? data.notify_alert_recovered,
    })
  }
  const visibleHistory = (history.data ?? []).filter(
    (item) => item.channel === "TELEGRAM" && (item.event_type === "OPEN" || item.event_type === "RECOVERED"),
  )

  return <div className="space-y-6">
    <div>
      <h2 className="text-2xl font-bold">Thông báo & Telegram</h2>
      <p className="text-sm text-muted-foreground">Telegram chỉ gửi sự cố vận hành thực sự; mức rủi ro được giữ để mô tả cảnh báo, không dùng để lọc người nhận.</p>
    </div>

    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2"><Bot className="size-5 text-primary" />Telegram cảnh báo</CardTitle>
            <CardDescription>Mỗi sự cố gửi tối đa một tin khi phát sinh và một tin khi trở lại bình thường.</CardDescription>
          </div>
          <Badge variant={data.telegram_bot_configured ? "secondary" : "outline"}>
            {data.telegram_bot_configured ? "Bot đã cấu hình" : "Bot chưa cấu hình"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <Setting
          label="Gửi cảnh báo qua Telegram"
          description={data.telegram_bot_configured
            ? "Khi bật, sự cố mới sẽ được gửi tới các người nhận đang hoạt động."
            : "Backend chưa có Bot Token. Có thể lưu cấu hình nhưng Telegram chưa thể gửi."}
          checked={data.telegram_enabled}
          disabled={!can("notifications.settings.update") || save.isPending}
          onChange={(telegram_enabled) => patch({ telegram_enabled })}
        />
        <div className="border-t pt-5">
          <Setting
            label="Báo khi hệ thống trở lại bình thường"
            description="Chỉ gửi cho người nhận đã từng nhận cảnh báo mở của chính sự cố đó."
            checked={data.notify_alert_recovered}
            disabled={!can("notifications.settings.update") || save.isPending}
            onChange={(notify_alert_recovered) => patch({ notify_alert_recovered })}
          />
        </div>
        <div className="rounded-xl border bg-muted/35 p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-primary" />
            <div className="space-y-1">
              <p className="font-medium">Chống spam tự động</p>
              <p className="text-sm text-muted-foreground">Không nhắc lại khi lỗi vẫn tồn tại. Thêm hoặc bật lại người nhận không phát lại cảnh báo cũ. Activity, trạng thái thiết bị và ACK lệnh không được đẩy vào kênh Telegram cảnh báo.</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Người nhận Telegram</CardTitle>
            <CardDescription>Chỉ những người nhận đang bật mới nhận các sự cố phát sinh sau thời điểm được cấu hình.</CardDescription>
          </div>
          {can("notifications.recipients.create") ? <Button onClick={() => setEditing("new")}><Plus />Thêm người nhận</Button> : null}
        </div>
      </CardHeader>
      <CardContent>
        {data.recipients.length
          ? <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow><TableHead>Tên</TableHead><TableHead>Telegram Chat ID</TableHead><TableHead>Trạng thái</TableHead><TableHead className="text-right">Thao tác</TableHead></TableRow></TableHeader>
                <TableBody>{data.recipients.map((recipient) =>
                  <RecipientRow key={recipient.id} systemId={systemId} recipient={recipient} refresh={refresh} onEdit={() => setEditing(recipient)} onDelete={() => setDeleting(recipient)} />
                )}</TableBody>
              </Table>
            </div>
          : <EmptyState icon={Send} title="Chưa có người nhận Telegram" description="Thêm Chat ID của cá nhân hoặc nhóm vận hành. Việc thêm mới không gửi lại các cảnh báo đang mở." action={can("notifications.recipients.create") ? <Button onClick={() => setEditing("new")}><Plus />Thêm người nhận</Button> : undefined} />}
      </CardContent>
    </Card>

    {can("notifications.history.read") ? <Card>
      <CardHeader>
        <CardTitle>Lịch sử Telegram</CardTitle>
        <CardDescription>Chỉ hiển thị cảnh báo mới và thông báo trở lại bình thường; chi tiết kỹ thuật retry được thu gọn.</CardDescription>
      </CardHeader>
      <CardContent>
        {history.isLoading
          ? <Skeleton className="h-48" />
          : history.isError
            ? <EmptyState icon={BellRing} title="Không thể tải lịch sử Telegram" description={errorMessage(history.error)} />
            : visibleHistory.length
              ? <div className="overflow-x-auto">
                  <Table>
                    <TableHeader><TableRow><TableHead>Thời gian</TableHead><TableHead>Sự kiện</TableHead><TableHead>Người nhận</TableHead><TableHead>Trạng thái</TableHead><TableHead>Chi tiết</TableHead></TableRow></TableHeader>
                    <TableBody>{visibleHistory.map((item) => <HistoryRow key={item.id} item={item} />)}</TableBody>
                  </Table>
                </div>
              : <EmptyState icon={BellRing} title="Chưa có lịch sử Telegram" description="Khi có sự cố mới hoặc sự cố trở lại bình thường, kết quả gửi sẽ xuất hiện tại đây." />}
      </CardContent>
    </Card> : null}

    <RecipientDialog key={editing === "new" ? "new" : editing?.id ?? "closed"} systemId={systemId} value={editing} onClose={() => setEditing(null)} onSaved={refresh} />

    <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => { if (!open) setDeleting(null) }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Xóa {deleting?.name}?</AlertDialogTitle>
          <AlertDialogDescription>Người nhận này sẽ không nhận các cảnh báo phát sinh sau khi bị xóa.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Hủy</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => { if (deleting) void removeRecipient(systemId, deleting, refresh).then(() => setDeleting(null)) }}>Xóa</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
}

function Setting({ label, description, checked, disabled, onChange }: { label: string; description: string; checked: boolean; disabled: boolean; onChange: (value: boolean) => void }) {
  return <div className="flex items-center justify-between gap-5"><div><p className="font-medium">{label}</p><p className="mt-1 text-sm text-muted-foreground">{description}</p></div><Switch checked={checked} disabled={disabled} onCheckedChange={onChange} aria-label={label} /></div>
}

function RecipientRow({ systemId, recipient, refresh, onEdit, onDelete }: { systemId: string; recipient: AlertDeliveryRecipient; refresh: () => Promise<void>; onEdit: () => void; onDelete: () => void }) {
  const { can } = useAuth()
  const update = useMutation({
    mutationFn: (enabled: boolean) => updateAlertDeliveryRecipient(systemId, recipient.id, { enabled }),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error)),
  })
  const test = useMutation({
    mutationFn: () => testAlertDeliveryRecipient(systemId, recipient.id),
    onSuccess: (result) => toast.success(result.detail),
    onError: (error) => toast.error(errorMessage(error)),
  })
  return <TableRow>
    <TableCell className="font-medium">{recipient.name}</TableCell>
    <TableCell className="font-mono">{recipient.telegram_chat_id}</TableCell>
    <TableCell><Switch checked={recipient.enabled} disabled={!can("notifications.recipients.update") || update.isPending} onCheckedChange={(enabled) => update.mutate(enabled)} aria-label={recipient.enabled ? `Tắt ${recipient.name}` : `Bật ${recipient.name}`} /></TableCell>
    <TableCell><div className="flex justify-end gap-2">
      {can("notifications.recipients.test") ? <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={!recipient.enabled || test.isPending}><Send />Gửi thử</Button> : null}
      {can("notifications.recipients.update") ? <Button size="icon" variant="outline" onClick={onEdit} aria-label={`Sửa ${recipient.name}`}><Pencil /></Button> : null}
      {can("notifications.recipients.delete") ? <Button size="icon" variant="destructive" onClick={onDelete} aria-label={`Xóa ${recipient.name}`}><Trash2 /></Button> : null}
    </div></TableCell>
  </TableRow>
}

async function removeRecipient(systemId: string, recipient: AlertDeliveryRecipient, refresh: () => Promise<void>) {
  try {
    await deleteAlertDeliveryRecipient(systemId, recipient.id)
    await refresh()
    toast.success("Đã xóa người nhận")
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

function HistoryRow({ item }: { item: AlertDeliveryHistoryItem }) {
  return <TableRow>
    <TableCell className="whitespace-nowrap">{new Date(item.created_at).toLocaleString("vi-VN")}</TableCell>
    <TableCell className="font-medium">{item.event_type === "RECOVERED" ? "Trở lại bình thường" : "Cảnh báo mới"}{item.incident_id ? <span className="ml-2 text-xs font-normal text-muted-foreground">#{item.incident_id}</span> : null}</TableCell>
    <TableCell>{item.recipient_name}</TableCell>
    <TableCell><StatusBadge value={item.status} /></TableCell>
    <TableCell className="max-w-96 text-sm text-muted-foreground">{historyDetail(item)}</TableCell>
  </TableRow>
}

function historyDetail(item: AlertDeliveryHistoryItem): string {
  if (item.status === "SENT") return "Đã gửi thành công"
  if (item.error_message) return item.error_message
  const reason = item.skip_reason ?? item.error_code ?? item.reason
  const labels: Record<string, string> = {
    NO_RECIPIENT: "Chưa có người nhận đang bật",
    BOT_NOT_CONFIGURED: "Bot Telegram chưa được cấu hình",
    TELEGRAM_DISABLED: "Telegram đang tắt",
    NOTIFICATIONS_DISABLED: "Hệ thống thông báo đang tắt",
    RECOVERY_DISABLED: "Thông báo phục hồi đang tắt",
    NO_PRIOR_OPEN_DELIVERY: "Không gửi phục hồi vì người nhận chưa từng nhận cảnh báo mở",
    RECIPIENT_DISABLED: "Người nhận đã bị tắt",
    SUPPRESSED_BY_DEVICE_OFFLINE: "Bỏ qua vì dữ liệu cũ trong lúc thiết bị offline",
    DUPLICATE_OPEN_EVENT: "Đã gửi cảnh báo này trước đó",
    DUPLICATE_INCIDENT_EVENT: "Đã gửi sự kiện này trước đó",
    INCIDENT_ONLY: "Kênh Telegram chỉ nhận cảnh báo sự cố",
    EVENT_DISABLED: "Loại sự kiện này không được gửi Telegram",
  }
  return reason ? labels[reason] ?? reason : "—"
}

function RecipientDialog({ systemId, value, onClose, onSaved }: { systemId: string; value: AlertDeliveryRecipient | "new" | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const source = value && value !== "new" ? value : null
  const [name, setName] = useState(source?.name ?? "")
  const [chatId, setChatId] = useState(source?.telegram_chat_id ?? "")
  const mutation = useMutation({
    mutationFn: () => value === "new"
      ? addAlertDeliveryRecipient(systemId, { name: name.trim(), telegram_chat_id: chatId.trim() })
      : updateAlertDeliveryRecipient(systemId, source!.id, { name: name.trim(), telegram_chat_id: chatId.trim() }),
    onSuccess: async () => {
      await onSaved()
      toast.success(value === "new" ? "Đã thêm người nhận" : "Đã cập nhật người nhận")
      onClose()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
  return <Dialog open={value !== null} onOpenChange={(open) => { if (!open) onClose() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{value === "new" ? "Thêm người nhận Telegram" : "Sửa người nhận Telegram"}</DialogTitle>
        <DialogDescription>Nhập tên gợi nhớ và Telegram Chat ID. Nhóm/supergroup thường có Chat ID âm.</DialogDescription>
      </DialogHeader>
      <div className="space-y-4">
        <div><Label htmlFor="delivery-name">Tên người nhận</Label><Input id="delivery-name" className="mt-1" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ví dụ: Nhóm vận hành" /></div>
        <div><Label htmlFor="delivery-chat">Telegram Chat ID</Label><Input id="delivery-chat" className="mt-1 font-mono" value={chatId} onChange={(event) => setChatId(event.target.value)} placeholder="Ví dụ: -1001234567890" /></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={onClose}>Hủy</Button><Button disabled={!name.trim() || !chatId.trim() || mutation.isPending} onClick={() => mutation.mutate()}>Lưu</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}
