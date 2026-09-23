import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { PowerOff, RotateCcw, Save, Settings } from "lucide-react"
import { useOutletContext, useParams } from "react-router-dom"
import { activateSystem, disableSystem, queryKeys, updateSystem } from "@/api/resources"
import type { AquaponicsSystem, AquaponicsSystemUpdate } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/shared/ui/alert-dialog"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"
import { Textarea } from "@/shared/ui/textarea"

export function SettingsPage() {
  const systemId = useParams().systemId ?? ""
  const validId = Boolean(systemId)
  const { system } = useOutletContext<{ system: AquaponicsSystem }>()
  const { can } = useAuth()
  const client = useQueryClient()
  const [systemDraft, setSystemDraft] = useState<AquaponicsSystemUpdate>({})
  const [lifecycleReason, setLifecycleReason] = useState("")
  const disabled = system.status === "DISABLED"

  useEffect(() => {
    setSystemDraft({ name: system.name, location: system.location, description: system.description })
  }, [system])

  const saveSystem = useMutation({
    mutationFn: () => updateSystem(systemId, systemDraft),
    onSuccess: async (value) => {
      client.setQueryData(queryKeys.system(systemId), value)
      await client.invalidateQueries({ queryKey: queryKeys.systems })
    },
  })

  const lifecycle = useMutation({
    mutationFn: (reason?: string) => disabled ? activateSystem(systemId) : disableSystem(systemId, { reason }),
    onSuccess: async () => {
      setLifecycleReason("")
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.system(systemId) }),
        client.invalidateQueries({ queryKey: queryKeys.systems }),
      ])
    },
  })

  if (!validId) {
    return <EmptyState icon={Settings} title="Đường dẫn hệ thống không hợp lệ" description="System ID không hợp lệ." />
  }

  return <div className="max-w-3xl space-y-6">

    <div>
      <h2 className="text-xl font-semibold">Thiết lập hệ thống</h2>
      <p className="text-sm text-muted-foreground">Thông tin và cấu hình hệ thống. Telegram được quản lý riêng tại tab Thông báo.</p>
    </div>

    <Card>
      <CardHeader><CardTitle>Thông tin hệ thống</CardTitle></CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); saveSystem.mutate() }}>
          <div><p className="text-sm text-muted-foreground">Mã hệ thống</p><p className="mt-1 font-mono font-medium">{system.code}</p></div>
          <TextField id="settings-name" label="Tên hệ thống" value={systemDraft.name ?? ""} onChange={(name) => setSystemDraft((current) => ({ ...current, name }))} />
          <TextField id="settings-location" label="Vị trí" required={false} value={systemDraft.location ?? ""} onChange={(location) => setSystemDraft((current) => ({ ...current, location }))} />
          <div><Label htmlFor="settings-description">Mô tả</Label><Textarea id="settings-description" className="mt-1" value={systemDraft.description ?? ""} onChange={(event) => setSystemDraft((current) => ({ ...current, description: event.target.value }))} /></div>
          {can("aquaponics_systems.update") ? <div className="flex justify-end sm:col-span-2"><Button type="submit" disabled={saveSystem.isPending}><Save />Lưu thông tin</Button></div> : null}
          {saveSystem.isError ? <p role="alert" className="text-sm text-destructive sm:col-span-2">{errorMessage(saveSystem.error)}</p> : null}
        </form>
      </CardContent>
    </Card>

    {can("aquaponics_systems.manage_all") ? <Card className="border-destructive/30">

      <CardHeader><CardTitle className="text-destructive">Vùng nguy hiểm</CardTitle></CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="font-medium">{disabled ? "Hệ thống đang vô hiệu hóa" : "Vô hiệu hóa hệ thống"}</p>
          <p className="text-sm text-muted-foreground">
            {disabled ? "Dữ liệu vẫn được giữ nguyên. Kích hoạt lại để tiếp tục vận hành." : "Dừng vận hành hệ thống mà không xóa dữ liệu. Có thể kích hoạt lại sau."}
          </p>
        </div>
        {disabled ? <Button type="button" variant="outline" disabled={lifecycle.isPending} onClick={() => lifecycle.mutate(undefined)}><RotateCcw />Kích hoạt lại hệ thống</Button> : <AlertDialog>
          <AlertDialogTrigger asChild><Button variant="destructive"><PowerOff />Vô hiệu hóa hệ thống</Button></AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Vô hiệu hóa {system.name}?</AlertDialogTitle>
              <AlertDialogDescription>Hệ thống sẽ dừng vận hành nhưng toàn bộ dữ liệu lịch sử vẫn được giữ lại.</AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-2">
              <Label htmlFor="disable-system-reason">Lý do vô hiệu hóa</Label>
              <Textarea id="disable-system-reason" value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Nhập ít nhất 3 ký tự" />
            </div>

            <AlertDialogFooter>
              <AlertDialogCancel>Huỷ</AlertDialogCancel>
              <AlertDialogAction variant="destructive" disabled={lifecycleReason.trim().length < 3 || lifecycle.isPending} onClick={() => lifecycle.mutate(lifecycleReason.trim())}>Xác nhận vô hiệu hóa</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>}
        {lifecycle.isError ? <p role="alert" className="w-full text-sm text-destructive">{errorMessage(lifecycle.error)}</p> : null}
      </CardContent>
    </Card> : null}
  </div>
}

function TextField({ id, label, value, onChange, required = true }: { id: string; label: string; value: string; onChange: (value: string) => void; required?: boolean }) {
  return <div><Label htmlFor={id}>{label}</Label><Input id={id} className="mt-1" value={value} onChange={(event) => onChange(event.target.value)} required={required} /></div>
}
