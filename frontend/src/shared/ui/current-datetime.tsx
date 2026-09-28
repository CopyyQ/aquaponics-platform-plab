import { useEffect, useState } from "react"
import { formatVietnamClock, formatVietnamDate, msUntilNextMinute } from "@/shared/lib/date"

/**
 * Ngày giờ hiện tại theo giờ Việt Nam, tự nhảy khi sang phút mới.
 * Hẹn đúng đầu phút kế tiếp thay vì đếm lùi mỗi giây, nên gần như không tốn gì.
 */
export function CurrentDateTime({ className }: { className?: string }) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setTimeout(() => setNow(new Date()), msUntilNextMinute(now))
    return () => window.clearTimeout(timer)
  }, [now])

  return (
    <time dateTime={now.toISOString()} className={className}>
      {formatVietnamDate(now)}
      <span className="ml-3 tabular-nums">{formatVietnamClock(now)}</span>
    </time>
  )
}
