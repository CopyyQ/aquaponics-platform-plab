import { AlertTriangle } from "lucide-react"
import type { ScadaIssue } from "@/api/contracts"
import { formatDateTime, formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Card } from "@/shared/ui/card"

/**
 * Sự cố thiết bị đang diễn ra: mất kết nối, không phản hồi lệnh, lệch đồng bộ,
 * dữ liệu ngoài miền hợp lệ.
 *
 * Khác hẳn cảnh báo ngưỡng ở bên dưới: những sự cố này không có bản ghi trong cơ sở
 * dữ liệu, được suy ra từ dữ liệu vận hành mỗi lần tải trang. Vì vậy chúng không có
 * lịch sử, không bấm xác nhận được, và tự biến mất khi điều kiện hết.
 *
 * Để riêng một khối thay vì trộn vào danh sách cảnh báo là có chủ ý: danh sách đó
 * gắn với thao tác xác nhận xử lý, mà những dòng này thì không thao tác được.
 */

const TONE: Record<ScadaIssue["severity"], { card: string; badge: string; icon: string; title: string; body: string }> = {
  CRITICAL: { card: "bg-rose-50", badge: "bg-rose-100 text-rose-700", icon: "bg-rose-100 text-rose-600", title: "text-rose-900", body: "text-rose-700" },
  HIGH: { card: "bg-rose-50", badge: "bg-rose-100 text-rose-700", icon: "bg-rose-100 text-rose-600", title: "text-rose-900", body: "text-rose-700" },
  WARNING: { card: "bg-amber-50", badge: "bg-amber-100 text-amber-700", icon: "bg-amber-100 text-amber-600", title: "text-amber-900", body: "text-amber-700" },
  INFO: { card: "bg-white", badge: "bg-slate-100 text-slate-600", icon: "bg-slate-100 text-slate-500", title: "text-slate-800", body: "text-slate-500" },
}

const SEVERITY_LABEL: Record<ScadaIssue["severity"], string> = {
  CRITICAL: "Nghiêm trọng",
  HIGH: "Nghiêm trọng",
  WARNING: "Cảnh báo",
  INFO: "Thông tin",
}

function DeviceIssueCard({ issue }: { issue: ScadaIssue }) {
  const tone = TONE[issue.severity]
  return (
    <Card className={cn("rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]", tone.card)}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={cn("grid size-10 shrink-0 place-items-center rounded-full", tone.icon)}>
            <AlertTriangle className="size-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h3 className={cn("font-semibold", tone.title)}>{issue.title}</h3>
            {/* Bỏ hẳn root_cause và current_state: chúng in ra nguyên văn kỹ thuật
                ("Lệnh gần nhất: FAILED", "Mong muốn: false; thực tế: false") — chủ hệ
                thống không đọc được mã trạng thái lẫn true/false. Tiêu đề đã gọi tên
                thiết bị, còn việc cần làm thì nằm ở dòng dưới. */}
            <p className={cn("mt-1 text-sm leading-6", tone.body)}>Nên làm: {issue.suggested_action}</p>
            {issue.timestamp ? (
              <p className="mt-2 text-xs text-slate-400">
                {formatRelative(issue.timestamp)} · {formatDateTime(issue.timestamp)}
              </p>
            ) : null}
          </div>
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide uppercase", tone.badge)}>
          {SEVERITY_LABEL[issue.severity]}
        </span>
      </div>
    </Card>
  )
}

export function OperatorDeviceIssuesBoard({ issues }: { issues: readonly ScadaIssue[] }) {
  if (!issues.length) return null
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-xs font-semibold tracking-[0.16em] text-slate-400 uppercase">Sự cố thiết bị đang diễn ra</h2>
        {/* Nói thẳng rằng đây không phải cảnh báo có sổ sách, để không ai chờ nó xuất hiện
            trong lịch sử hay trong tin nhắn Telegram. */}
        <p className="mt-1 text-xs text-slate-400">
          Theo dõi trực tiếp từ dữ liệu vận hành. Những sự cố này không được lưu thành bản ghi và tự hết khi thiết bị trở lại bình thường.
        </p>
      </div>
      {issues.map((issue) => <DeviceIssueCard key={issue.id} issue={issue} />)}
    </section>
  )
}
