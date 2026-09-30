/**
 * Các mạch nước vẽ chồng lên tranh SCADA.
 *
 * Toạ độ trong `d` theo hệ pixel của tranh gốc 1750×1100, khớp thẳng với viewBox của
 * lớp SVG. Đường đi lấy từ bước vạch tay trên trang hiệu chỉnh, men theo tim ống
 * đã vẽ sẵn trong tranh.
 */
export type ScadaFlowTone = "sky" | "emerald" | "violet" | "amber" | "rose"

export interface ScadaFlow {
  id: string
  name: string
  /**
   * Trang hiệu chỉnh vẫn xuất trường này để phân biệt mạch lúc vạch, nhưng lớp vẽ
   * dùng chung một màu xanh cho mọi mạch: tranh nền đã nhiều màu, thêm năm màu nữa
   * thì đường nước lẫn vào thiết bị và chọi với màu báo trạng thái của các thẻ.
   */
  tone?: ScadaFlowTone
  /**
   * Mã cơ cấu quyết định mạch có chảy hay không.
   *
   * `null` nghĩa là chưa gắn với thiết bị nào nên mạch chảy liên tục — chỉ dùng khi
   * đang dựng hình. Gắn được cơ cấu thì mạch mới nói đúng chuyện đang xảy ra ngoài vườn.
   */
  actuator: string | null
  /** Đảo chiều chảy khi đường được vạch ngược với hướng nước đi. */
  reverse?: boolean
  /** Đường đi dạng thuộc tính `d` của SVG path. */
  d: string
}

/**
 * Chiều dài đường gấp khúc, tính thẳng từ chuỗi `d`.
 *
 * Mọi mạch đều là đường gấp khúc M/L nên đo được bằng công thức, không cần dựng DOM
 * rồi gọi getTotalLength. Nhờ vậy số mũi tên rải đều theo chiều dài thật: mạch dài
 * nhiều mũi tên, mạch ngắn ít, khoảng cách giữa chúng luôn như nhau.
 */
export function polylineLength(d: string) {
  const nums = d.replace(/[ML]/g, " ").trim().split(/\s+/).map(Number)
  let total = 0
  for (let i = 2; i + 1 < nums.length; i += 2) {
    total += Math.hypot(nums[i] - nums[i - 2], nums[i + 1] - nums[i - 1])
  }
  return total
}

export const SCADA_FLOWS: ScadaFlow[] = [
  // Nhánh cấp nước sạch: chỉ chảy khi van cấp nước mở. Tách làm hai đoạn, chừa khoảng
  // trống ngay chỗ van đỏ vẽ trên tranh để nước không chảy đè lên hình cái van.
  { id: "flow-1", name: "Bồn nước vào bể cá — trước van", actuator: "FRESH_WATER_VALVE", d: "M 235.2 738.6 L 267.6 738.6" },
  { id: "flow-10", name: "Bồn nước vào bể cá — sau van", actuator: "FRESH_WATER_VALVE", d: "M 306.6 738.6 L 378.1 738.6 L 378.1 808.8" },

  // Vòng tuần hoàn chính do bơm bể cá đẩy: lên bể lọc rồi theo ống trái quay về bể cá.
  // Hai đoạn này là một mạch, tắt bơm là cả vòng dừng.
  { id: "flow-11", name: "Bể cá lên bể lọc", actuator: "FISH_TANK_PUMP", d: "M 888.6 937.4 L 888.6 476.2 L 673.0 474.9 L 671.7 315.1" },
  { id: "flow-3", name: "Bể lọc về bể cá", actuator: "FISH_TANK_PUMP", d: "M 619.7 337.1 L 445.6 338.4 L 443.0 791.9" },

  // Bơm trong bồn chứa đẩy nước lên giàn cây rồi nhận lại.
  { id: "flow-14", name: "Bồn chứa lên giàn cây", actuator: "BIOFILTER_PUMP", d: "M 1070.5 500.8 L 1070.5 237.1 L 1364.1 238.4 L 1387.5 286.5" },
  { id: "flow-15", name: "Giàn cây về bồn chứa", actuator: "BIOFILTER_PUMP", d: "M 1426.5 471.0 L 1426.5 495.6 L 1112.1 495.6" },

  // Hai nhánh dưới đây đi qua van tay vẽ trên tranh — van tưới và van dưới bể lọc.
  // Chưa có cơ cấu nào trong cơ sở dữ liệu ứng với chúng nên tạm cho chảy liên tục;
  // khi nào đấu cảm biến vào thì điền mã cơ cấu là mạch tự bám trạng thái thật.
  { id: "flow-12", name: "Qua van tưới", actuator: null, d: "M 718.4 337.1 L 828.9 337.1" },
  { id: "flow-13", name: "Van tưới sang bồn chứa", actuator: null, d: "M 869.2 337.1 L 983.5 337.1" },
  { id: "flow-16", name: "Bể lọc xuống giàn rau", actuator: null, d: "M 549.6 486.6 L 508.0 485.3 L 505.4 693.1" },
  { id: "flow-17", name: "Giàn rau xuống bể cá", actuator: null, d: "M 800.3 710.0 L 799.0 756.8" },
]
