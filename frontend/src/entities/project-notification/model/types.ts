export interface NotificationRecipient {
  id: number
  name: string
  telegram_chat_id: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type BusinessRiskLevel =
  | "EXTREME"
  | "VERY_HIGH"
  | "HIGH"
  | "MEDIUM"
  | "LOW_MEDIUM"
  | "LOW"

export interface NotificationSettings {
  telegram_enabled: boolean
  notify_alert_recovered: boolean
  telegram_bot_configured: boolean
  recipients: NotificationRecipient[]
}

export interface NotificationDelivery {
  id: number
  created_at: string
  project_id: number
  project_name: string
  rule_name: string
  business_risk_level: BusinessRiskLevel
  channel: string
  recipient_name: string
  status: "PENDING" | "SENT" | "FAILED" | "RETRYING" | "SKIPPED"
  attempt_count: number
  reason: string | null
}

export interface PublicSettings {
  enabled: boolean
  remote_monitoring_available: boolean
}
