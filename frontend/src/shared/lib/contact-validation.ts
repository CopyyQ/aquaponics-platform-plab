import { z } from "zod"

export const vietnameseMobilePattern = /^(?:0|\+84)[35789][0-9]{8}$/
export const gmailDomain = "gmail.com"

export function isVietnameseMobilePhone(value: string): boolean {
  return vietnameseMobilePattern.test(value.trim())
}

export function normalizeVietnameseMobilePhone(value: string): string {
  const trimmed = value.trim()
  return trimmed.startsWith("+84") ? `0${trimmed.slice(3)}` : trimmed
}

export function isGmailAddress(value: string): boolean {
  const normalized = value.trim().toLowerCase()
  const at = normalized.lastIndexOf("@")
  return at > 0 && normalized.slice(at + 1) === gmailDomain
}

export const vietnameseMobileSchema = z
  .string()
  .trim()
  .refine(
    isVietnameseMobilePhone,
    "Số điện thoại phải là số di động Việt Nam 10 số, bắt đầu bằng 03/05/07/08/09 hoặc +84 tương ứng",
  )
  .transform(normalizeVietnameseMobilePhone)

export const gmailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .email("Email không đúng định dạng")
  .refine(isGmailAddress, "Email phải sử dụng địa chỉ Gmail (@gmail.com)")
