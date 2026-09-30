import { describe, expect, it } from "vitest"

import { createAccountSchema } from "./create-account.schema"

const basePayload = {
  username: "contact.validation",
  full_name: "Nguyễn Văn A",
  email: "contact.validation@gmail.com",
  phone_number: "0912345678",
  address: "Hà Nội",
  system_role: "VIEWER" as const,
  status: "ACTIVE" as const,
  password: "RequiredInfo@123",
  confirm_password: "RequiredInfo@123",
  must_change_password: true,
}

describe("createAccountSchema contact validation", () => {
  it("accepts Vietnamese mobile numbers and normalizes +84 to 0", () => {
    const parsed = createAccountSchema.parse({
      ...basePayload,
      phone_number: "+84912345678",
    })

    expect(parsed.phone_number).toBe("0912345678")
  })

  it.each([
    "0612345678",
    "0212345678",
    "091234567",
    "09123456789",
    "+12345678901",
    "0912 345 678",
  ])("rejects non-Vietnamese mobile number %s", (phone_number) => {
    expect(() => createAccountSchema.parse({ ...basePayload, phone_number })).toThrow()
  })

  it("requires gmail.com and normalizes email case", () => {
    const parsed = createAccountSchema.parse({
      ...basePayload,
      email: "  Contact.Validation@GMAIL.COM  ",
    })

    expect(parsed.email).toBe("contact.validation@gmail.com")
    expect(() =>
      createAccountSchema.parse({
        ...basePayload,
        email: "contact.validation@yahoo.com",
      }),
    ).toThrow()
  })
})
