// Bố cục thẻ dữ liệu phủ lên ảnh SCADA.
// Toạ độ theo phần trăm của khung ảnh 1500x1000 (tỉ lệ 3:2), lấy từ bước hiệu chỉnh thủ công.
// Chỉ số bind theo sensor_model_code / actuator_model_code nên dùng chung được cho mọi hệ thống.

export type ScadaMetricKind = "SENSOR" | "ACTUATOR" | "DERIVED"
export type ScadaCardIcon = "droplets" | "waves" | "fish"

export interface ScadaMetric {
  code: string
  kind: ScadaMetricKind
  /** Tên ngắn cho mặt thẻ trên sơ đồ, nơi bề ngang rất hẹp. */
  label: string
  /**
   * Tên đầy đủ cho hộp chi tiết, viết theo cách chủ hệ thống hiểu được,
   * thuật ngữ kỹ thuật để trong ngoặc. Bỏ trống thì dùng lại label.
   */
  fullLabel?: string
  /** Đơn vị cố định cho chỉ số tính toán; chỉ số đo lấy đơn vị từ inventory. */
  unit?: string
}

export interface ScadaCard {
  id: string
  title: string | null
  box: { x: number; y: number; w: number; h: number }
  /**
   * Cạnh được giữ cố định khi thẻ cao hơn khung đã vẽ.
   * "bottom" dùng cho thẻ đặt phía trên thiết bị: thẻ nở ngược lên khoảng trống
   * thay vì trùm xuống hình. Mặc định "top".
   */
  anchor?: "top" | "bottom"
  /** Chỉ hiện giá trị, bỏ nhãn — dùng cho đồng hồ đã có nhãn vẽ sẵn trên tranh. */
  valueOnly?: boolean
  /**
   * Xếp nhãn trên, giá trị dưới thay vì hai bên. Dùng cho thẻ hẹp: cả dòng
   * dành cho nhãn nên không bị cắt cụt, đổi lại thẻ cao gấp đôi.
   */
  stacked?: boolean
  /** Biểu tượng trong huy hiệu tròn cạnh tiêu đề. */
  icon?: ScadaCardIcon
  items: string[]
}

/** Công suất không có cảm biến riêng, tính từ điện áp nhân dòng điện. */
export const DERIVED_POWER = "POWER"

export const SCADA_METRICS: ScadaMetric[] = [
  { code: "WATER_TEMPERATURE", kind: "SENSOR", label: "Nhiệt độ nước" },
  { code: "PH", kind: "SENSOR", label: "Độ pH", fullLabel: "Độ pH (chua – kiềm)" },
  { code: "DO", kind: "SENSOR", label: "Oxy hòa tan", fullLabel: "Oxy hòa tan (DO)" },
  { code: "WATER_LEVELW2", kind: "SENSOR", label: "Mực nước", fullLabel: "Mực nước bể cá" },
  { code: "WATER_LEVEL", kind: "SENSOR", label: "Mực nước", fullLabel: "Mực nước bể lọc" },
  { code: "TDS", kind: "SENSOR", label: "Dinh dưỡng", fullLabel: "Dinh dưỡng tổng (TDS)" },
  { code: "NO3", kind: "SENSOR", label: "Đạm nitrat", fullLabel: "Đạm nitrat (NO3)" },
  { code: "NH3", kind: "SENSOR", label: "Amoniac", fullLabel: "Amoniac (NH3)" },
  { code: "AIR_TEMPERATURE", kind: "SENSOR", label: "Nhiệt độ", fullLabel: "Nhiệt độ không khí" },
  { code: "AIR_HUMIDITY", kind: "SENSOR", label: "Độ ẩm", fullLabel: "Độ ẩm không khí" },
  { code: "LIGHT_INTENSITY", kind: "SENSOR", label: "Ánh sáng", fullLabel: "Cường độ ánh sáng" },
  { code: "VOLTAGE", kind: "SENSOR", label: "Điện áp" },
  { code: "CURRENT", kind: "SENSOR", label: "Dòng điện" },
  { code: DERIVED_POWER, kind: "DERIVED", label: "Công suất", fullLabel: "Công suất tiêu thụ", unit: "W" },
  { code: "FISH_TANK_PUMP", kind: "ACTUATOR", label: "Bơm bể cá" },
  { code: "AERATION_PUMP", kind: "ACTUATOR", label: "Máy sủi oxy" },
  { code: "BIOFILTER_PUMP", kind: "ACTUATOR", label: "Bơm bể lọc" },
  { code: "FILTER_DRAIN_VALVE", kind: "ACTUATOR", label: "Van xả đáy" },
  { code: "FRESH_WATER_VALVE", kind: "ACTUATOR", label: "Van cấp nước" },
  { code: "GROW_LIGHT", kind: "ACTUATOR", label: "Đèn chiếu sáng" },
  { code: "WARNING_LIGHT", kind: "ACTUATOR", label: "Đèn cảnh báo" },
  { code: "WARNING_BUZZER", kind: "ACTUATOR", label: "Loa/còi báo" },
]

export const SCADA_CARDS: ScadaCard[] = [
  {
    id: "biofilter",
    title: "Bể lọc vi sinh",
    box: { x: 29.32, y: 7.18, w: 15.06, h: 9.25 },
    anchor: "bottom",
    icon: "droplets",
    items: ["WATER_LEVEL", "TDS", "NO3", "NH3"],
  },
  {
    id: "water-supply",
    title: "Van & bơm",
    box: { x: 51.8, y: 6.87, w: 12.82, h: 8.3 },
    anchor: "bottom",
    icon: "waves",
    items: ["FRESH_WATER_VALVE", "BIOFILTER_PUMP", "FILTER_DRAIN_VALVE"],
  },
  {
    id: "fish-tank",
    title: "Bể cá",
    box: { x: 2.8, y: 66.72, w: 9.48, h: 21.82 },
    stacked: true,
    icon: "fish",
    items: ["WATER_TEMPERATURE", "PH", "DO", "WATER_LEVELW2"],
  },
  // Sáu đồng hồ trên tủ điện: nhãn đã vẽ sẵn trên tranh nên chỉ đổ số.
  {
    id: "meter-grid",
    title: null,
    box: { x: 68.83, y: 60.88, w: 7.01, h: 7.25 },
    valueOnly: true,
    items: ["VOLTAGE", "CURRENT"],
  },
  {
    id: "meter-power",
    title: null,
    box: { x: 81.44, y: 60.04, w: 6.8, h: 4.73 },
    valueOnly: true,
    items: [DERIVED_POWER],
  },
  // Bốn đồng hồ dưới đây chưa có cảm biến nào trong hệ thống, để trống thay vì bịa số.
  { id: "meter-solar", title: null, box: { x: 69.39, y: 76.01, w: 6, h: 4 }, valueOnly: true, items: [] },
  { id: "meter-battery", title: null, box: { x: 81.93, y: 75.91, w: 6, h: 4 }, valueOnly: true, items: [] },
  { id: "meter-ac", title: null, box: { x: 69.39, y: 87.47, w: 6, h: 4 }, valueOnly: true, items: [] },
  { id: "meter-dc", title: null, box: { x: 81.58, y: 87.47, w: 6, h: 4 }, valueOnly: true, items: [] },
]

/**
 * Thẻ tình trạng hệ thống, chiếm chỗ của thẻ chỉ số không khí trước đây.
 * Không gắn chỉ số nào: nó tổng hợp sức khoẻ toàn hệ thống và dẫn sang trang cảnh báo.
 */
export const SCADA_SYSTEM_CARD = {
  id: "system",
  // Chỉ x và y được dùng: thẻ tự co đúng bằng bề ngang dòng chữ dài nhất,
  // nên w và h giữ lại chỉ để ghi nhớ vùng đã dành cho nó lúc hiệu chỉnh.
  box: { x: 1.54, y: 2.41, w: 21, h: 16.06 },
} as const

/**
 * Cột đo mực nước bể cá, dựng dọc bên phải bể và cao đúng bằng bể.
 * Ảnh nền chỉ vẽ được hai mức 60% và 100%, nên cột này là chỗ duy nhất
 * thể hiện mực nước liên tục theo đúng số đo.
 */
export const SCADA_LEVEL_GAUGE = {
  code: "WATER_LEVELW2",
  box: { x: 54.23, y: 67.49, w: 2.22, h: 20.78 },
} as const

// Chưa hiển thị: AIR_TEMPERATURE, AIR_HUMIDITY, LIGHT_INTENSITY,
// FISH_TANK_PUMP, AERATION_PUMP, GROW_LIGHT, WARNING_LIGHT, WARNING_BUZZER.
// Những chỉ số này chưa được đánh dấu vị trí trên tranh. Thêm vào items của một thẻ
// hoặc tạo thẻ mới cho chúng khi đã có toạ độ.
