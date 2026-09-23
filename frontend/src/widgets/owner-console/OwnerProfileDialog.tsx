import { useEffect, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Eye, EyeOff, KeyRound, Save } from "lucide-react"
import { toast } from "sonner"
import type { SessionUser } from "@/api/contracts"
import { changePassword, updateProfile } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { OwnerDialog, OwnerDialogContent, OwnerDialogDescription, OwnerDialogTitle } from "./OwnerDialog"
import { Avatar, AvatarFallback } from "@/shared/ui/avatar"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"

const TEAL = "bg-[#0d5c4d] hover:bg-[#0b4d40] text-white"

function initialsOf(fullName: string | undefined) {
  return (fullName ?? "ND").split(" ").filter(Boolean).slice(-2).map((part) => part[0]).join("").toUpperCase()
}

function Field({ id, label, value, type = "text", onChange }: { id: string; label: string; value: string; type?: string; onChange: (value: string) => void }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs font-medium text-slate-600">{label}</Label>
      <Input id={id} className="h-10 rounded-xl" type={type} value={value} onChange={(event) => onChange(event.target.value)} required />
    </div>
  )
}

function PasswordField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs font-medium text-slate-600">{label}</Label>
      <div className="relative">
        <Input id={id} className="h-10 rounded-xl pr-10" type={visible ? "text" : "password"} minLength={8} value={value} onChange={(event) => onChange(event.target.value)} required />
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
          className="absolute inset-y-0 right-0 grid w-10 place-items-center text-slate-400 hover:text-[#0d5c4d]"
        >
          {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
        </button>
      </div>
    </div>
  )
}

export function OwnerProfileDialog({
  open,
  onOpenChange,
  user,
  onSaved,
  onPasswordChanged,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  user: SessionUser | undefined
  onSaved: () => Promise<void>
  onPasswordChanged: () => void
}) {
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [phoneNumber, setPhoneNumber] = useState("")
  const [address, setAddress] = useState("")
  const [saved, setSaved] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)

  // Nạp lại form mỗi lần mở modal để bỏ thay đổi chưa lưu
  useEffect(() => {
    if (open && user) {
      setFullName(user.full_name)
      setEmail(user.email)
      setPhoneNumber(user.phone_number)
      setAddress(user.address ?? "")
      setSaved(false)
    }
  }, [open, user])

  const profile = useMutation({
    mutationFn: () => updateProfile({ full_name: fullName.trim(), email: email.trim(), phone_number: phoneNumber.trim(), address: address.trim() }),
    onSuccess: async () => { await onSaved(); setSaved(true) },
  })

  return (
    <>
      <OwnerDialog open={open} onOpenChange={onOpenChange}>
        <OwnerDialogContent className="max-w-md p-0">
          <div className="flex items-center gap-4 px-6 pt-6">
            <Avatar className="size-14 bg-[#0d5c4d] text-white"><AvatarFallback className="bg-transparent text-lg font-semibold text-white">{initialsOf(user?.full_name)}</AvatarFallback></Avatar>
            <div className="min-w-0">
              <OwnerDialogTitle className="truncate text-lg font-semibold text-slate-900">{user?.full_name}</OwnerDialogTitle>
              <OwnerDialogDescription className="truncate text-xs text-slate-500">@{user?.username} · Chủ hệ thống</OwnerDialogDescription>
            </div>
          </div>
          <form className="space-y-3 px-6 pb-6" onSubmit={(event) => { event.preventDefault(); profile.mutate() }}>
            <Field id="owner-profile-name" label="Họ tên" value={fullName} onChange={setFullName} />
            <Field id="owner-profile-email" label="Email" type="email" value={email} onChange={setEmail} />
            <Field id="owner-profile-phone" label="Số điện thoại" type="tel" value={phoneNumber} onChange={setPhoneNumber} />
            <Field id="owner-profile-address" label="Địa chỉ" value={address} onChange={setAddress} />
            {saved ? <p role="status" className="text-sm text-emerald-700">Đã lưu thay đổi.</p> : null}
            {profile.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(profile.error)}</p> : null}
            <div className="flex items-center justify-between gap-3 pt-2">
              <Button type="button" variant="ghost" className="rounded-xl text-[#0d5c4d] hover:bg-[#0d5c4d]/10 hover:text-[#0d5c4d]" onClick={() => setPasswordOpen(true)}>
                <KeyRound className="size-4" />Đổi mật khẩu
              </Button>
              <Button type="submit" className={`rounded-xl ${TEAL}`} disabled={profile.isPending}>
                <Save className="size-4" />Lưu thay đổi
              </Button>
            </div>
          </form>
        </OwnerDialogContent>
      </OwnerDialog>

      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} onChanged={onPasswordChanged} />
    </>
  )
}

function ChangePasswordDialog({ open, onOpenChange, onChanged }: { open: boolean; onOpenChange: (open: boolean) => void; onChanged: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")

  useEffect(() => {
    if (open) { setCurrentPassword(""); setNewPassword(""); setConfirmPassword("") }
  }, [open])

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword
  const password = useMutation({
    mutationFn: () => changePassword({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
    onSuccess: () => {
      toast.success("Đổi mật khẩu thành công", { duration: 4000 })
      onChanged()
    },
  })

  return (
    <OwnerDialog open={open} onOpenChange={onOpenChange}>
      <OwnerDialogContent className="max-w-sm p-6">
        <div className="space-y-1">
          <OwnerDialogTitle className="flex items-center gap-2 text-base font-semibold text-slate-900"><KeyRound className="size-4 text-[#0d5c4d]" />Đổi mật khẩu</OwnerDialogTitle>
          <OwnerDialogDescription className="text-xs text-slate-500">Nhập mật khẩu hiện tại và mật khẩu mới (tối thiểu 8 ký tự).</OwnerDialogDescription>
        </div>
        <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); password.mutate() }}>
          <PasswordField id="owner-current-password" label="Mật khẩu hiện tại" value={currentPassword} onChange={setCurrentPassword} />
          <PasswordField id="owner-new-password" label="Mật khẩu mới" value={newPassword} onChange={setNewPassword} />
          <PasswordField id="owner-confirm-password" label="Xác nhận mật khẩu mới" value={confirmPassword} onChange={setConfirmPassword} />
          {mismatch ? <p role="alert" className="text-sm text-destructive">Mật khẩu xác nhận không khớp.</p> : null}
          {password.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(password.error)}</p> : null}
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">Sau khi đổi mật khẩu thành công, bạn sẽ được đăng xuất và cần đăng nhập lại.</p>
          <div className="flex justify-end pt-1">
            <Button type="submit" className={`rounded-xl ${TEAL}`} disabled={password.isPending || mismatch || newPassword.length < 8}>
              <KeyRound className="size-4" />Đổi mật khẩu
            </Button>
          </div>
        </form>
      </OwnerDialogContent>
    </OwnerDialog>
  )
}
