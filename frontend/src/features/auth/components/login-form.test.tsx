import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { LoginForm } from "./login-form"

describe("LoginForm account recovery options", () => {
  it("shows remember-password and forgot-password contact actions", () => {
    const html = renderToStaticMarkup(<LoginForm onSuccess={() => undefined} />)
    expect(html).toContain("Nhớ mật khẩu")
    expect(html).toContain("Quên mật khẩu?")
    expect(html).toContain("Liên hệ Quản trị viên")
  })
})
