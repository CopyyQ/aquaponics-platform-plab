import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import {
  AlertCircle,
  Eye,
  EyeOff,
  LoaderCircle,
  LifeBuoy,
  LockKeyhole,
  LogIn,
  UserRound,
} from "lucide-react"
import { toast } from "sonner"

import { errorMessage } from "@/api/client"
import { login as loginRequest } from "@/api/resources"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { Label } from "@/shared/ui/label"

const loginSchema = z.object({
  username: z.string().trim().min(1, "Vui lòng nhập tên đăng nhập").max(100),
  password: z.string().min(1, "Vui lòng nhập mật khẩu").max(256),
})

type LoginFormValues = z.infer<typeof loginSchema>

const REMEMBER_PASSWORD_KEY = "aquaponics_remember_password"
const REMEMBERED_USERNAME_KEY = "aquaponics_remembered_username"

function rememberedLogin() {
  if (typeof window === "undefined") return { enabled: false, username: "" }
  const enabled = localStorage.getItem(REMEMBER_PASSWORD_KEY) === "1"
  return { enabled, username: enabled ? localStorage.getItem(REMEMBERED_USERNAME_KEY) ?? "" : "" }
}

async function requestBrowserPasswordSave(username: string, password: string) {
  if (typeof window === "undefined" || typeof navigator === "undefined" || !navigator.credentials?.store) return
  const PasswordCredentialCtor = (window as typeof window & {
    PasswordCredential?: new (data: { id: string; name?: string; password: string }) => Credential
  }).PasswordCredential
  if (!PasswordCredentialCtor) return
  try {
    await navigator.credentials.store(new PasswordCredentialCtor({ id: username, name: username, password }))
  } catch {
    // Password persistence is owned by the browser; login must still succeed if it declines.
  }
}

function friendlyLoginError(error: unknown): string {
  const message = errorMessage(error)
  if (/401|unauthorized|không chính xác/i.test(message)) return "Tên đăng nhập hoặc mật khẩu không chính xác."
  if (/403|permission|không có quyền/i.test(message)) return "Tài khoản không được phép truy cập hệ thống."
  if (/disabled|inactive/i.test(message)) return "Tài khoản hiện không hoạt động. Vui lòng liên hệ Quản trị viên."
  if (/locked/i.test(message)) return "Tài khoản đang bị khóa. Vui lòng liên hệ Quản trị viên."
  return message
}

export function LoginForm({ onSuccess }: { onSuccess: () => void | Promise<void> }) {
  const remembered = rememberedLogin()
  const [showPassword, setShowPassword] = useState(false)
  const [rememberPassword, setRememberPassword] = useState(remembered.enabled)
  const [showRecoveryHelp, setShowRecoveryHelp] = useState(false)
  const {
    register,
    handleSubmit,
    clearErrors,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: { username: remembered.username, password: "" },
  })

  const usernameRegistration = register("username")
  const passwordRegistration = register("password")

  const onSubmit = handleSubmit(async (values) => {
    clearErrors("root")
    try {
      const username = values.username.trim()
      const result = await loginRequest(username, values.password)
      localStorage.setItem("aquaponics_access_token", result.access_token)
      if (rememberPassword) {
        localStorage.setItem(REMEMBER_PASSWORD_KEY, "1")
        localStorage.setItem(REMEMBERED_USERNAME_KEY, username)
        void requestBrowserPasswordSave(username, values.password)
      } else {
        localStorage.removeItem(REMEMBER_PASSWORD_KEY)
        localStorage.removeItem(REMEMBERED_USERNAME_KEY)
      }
      toast.success("Đăng nhập thành công", { description: "Đang chuyển đến trung tâm vận hành.", duration: 4000 })
      await onSuccess()
    } catch (error) {
      localStorage.removeItem("aquaponics_access_token")
      setError("root", { type: "server", message: friendlyLoginError(error) })
    }
  })

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
      <div className="flex flex-col gap-2">
        <Label htmlFor="username" className="text-sm font-medium">Tên đăng nhập</Label>
        <div className={[
          "group relative rounded-xl border bg-background transition-[border-color,box-shadow]",
          "focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10",
          errors.username ? "border-destructive/70" : "border-input",
        ].join(" ")}>
          <UserRound aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted-foreground transition-colors group-focus-within:text-primary" />
          <Input
            {...usernameRegistration}
            id="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            autoFocus
            disabled={isSubmitting}
            placeholder="Nhập tên đăng nhập hoặc email"
            aria-invalid={Boolean(errors.username)}
            aria-describedby={errors.username ? "username-error" : undefined}
            className="h-12 rounded-xl border-0 bg-transparent pl-11 pr-4 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onChange={(event) => { clearErrors("root"); usernameRegistration.onChange(event) }}
          />
        </div>
        {errors.username?.message ? <p id="username-error" role="alert" className="text-xs font-medium text-destructive">{errors.username.message}</p> : null}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password" className="text-sm font-medium">Mật khẩu</Label>
        <div className={[
          "group relative rounded-xl border bg-background transition-[border-color,box-shadow]",
          "focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10",
          errors.password ? "border-destructive/70" : "border-input",
        ].join(" ")}>
          <LockKeyhole aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted-foreground transition-colors group-focus-within:text-primary" />
          <Input
            {...passwordRegistration}
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            disabled={isSubmitting}
            placeholder="Nhập mật khẩu"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? "password-error" : undefined}
            className="h-12 rounded-xl border-0 bg-transparent pl-11 pr-12 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onChange={(event) => { clearErrors("root"); passwordRegistration.onChange(event) }}
          />
          <button
            type="button"
            disabled={isSubmitting}
            aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
            aria-pressed={showPassword}
            className="absolute right-1.5 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setShowPassword((current) => !current)}
          >
            {showPassword ? <EyeOff aria-hidden="true" className="size-5" /> : <Eye aria-hidden="true" className="size-5" />}
          </button>
        </div>
        {errors.password?.message ? <p id="password-error" role="alert" className="text-xs font-medium text-destructive">{errors.password.message}</p> : null}
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <label htmlFor="remember-password" className="inline-flex cursor-pointer items-center gap-2 text-slate-600">
            <input
              id="remember-password"
              type="checkbox"
              checked={rememberPassword}
              disabled={isSubmitting}
              onChange={(event) => setRememberPassword(event.target.checked)}
              className="size-4 rounded border-slate-300 accent-emerald-700"
            />
            <span>Nhớ mật khẩu</span>
          </label>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 font-medium text-[#08766c] hover:underline"
            aria-expanded={showRecoveryHelp}
            aria-controls="password-recovery-help"
            onClick={() => setShowRecoveryHelp((current) => !current)}
          >
            <LifeBuoy aria-hidden="true" className="size-4" />
            Quên mật khẩu? Liên hệ Quản trị viên
          </button>
        </div>

        <p className="text-xs leading-5 text-slate-500">
          Mật khẩu được lưu bởi trình quản lý mật khẩu của trình duyệt; ứng dụng không lưu mật khẩu thô.
        </p>

        {showRecoveryHelp ? (
          <div id="password-recovery-help" className="rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-emerald-950">
            Liên hệ Quản trị viên PLAB qua kênh nội bộ để được đặt lại mật khẩu. Chỉ cần cung cấp tên đăng nhập, không gửi mật khẩu cũ.
          </div>
        ) : null}
      </div>

      {errors.root?.message ? (
        <div role="alert" aria-live="polite" className="flex items-start gap-3 rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <span>{errors.root.message}</span>
        </div>
      ) : null}

      <Button type="submit" size="lg" className="h-12 rounded-xl" disabled={isSubmitting}>
        {isSubmitting ? <LoaderCircle aria-hidden="true" className="animate-spin" /> : <LogIn aria-hidden="true" />}
        {isSubmitting ? "Đang đăng nhập…" : "Đăng nhập"}
      </Button>
    </form>
  )
}
