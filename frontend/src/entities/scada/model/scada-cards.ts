// Bố cục thẻ dữ liệu phủ lên ảnh SCADA.
// Toạ độ theo phần trăm của khung ảnh, lấy từ bước hiệu chỉnh thủ công.
// Chỉ số bind theo sensor_model_code / actuator_model_code nên dùng chung được cho mọi hệ thống.

/**
 * Tỉ lệ khung ảnh nền, bằng đúng tỉ lệ của bộ tranh trong public/scada/scenarios (1750×1100).
 *
 * Khung phải khớp tỉ lệ tranh thì ảnh mới lấp đầy; lệch tỉ lệ sẽ sinh viền trên dưới và
 * mọi toạ độ phần trăm bên dưới lệch theo. Đổi bộ tranh thì sửa luôn con số này.
 */
export const SCADA_IMAGE_ASPECT = 1750 / 1100

export type ScadaMetricKind = "SENSOR" | "ACTUATOR" | "DERIVED"
export type ScadaCardIcon = "droplets" | "waves" | "fish" | "droplet" | "sprout"

export interface ScadaMetric {
  code: string
  kind: ScadaMetricKind
  /** Tên ngắn cho mặt thẻ trên sơ đồ, nơi bề ngang rất hẹp. */
  label: string
  /**
   * Tên dự phòng cho hộp chi tiết khi thiết bị không có trong dữ liệu trả về.
   * Bình thường hộp chi tiết lấy thẳng tên trong cơ sở dữ liệu, nên sửa tên bên
   * quản trị là nó đổi theo; chỉ mặt thẻ mới giữ tên ngắn vì bề ngang quá hẹp.
   *
   * Viết theo cách chủ hệ thống hiểu được,
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
  /**
   * Mặt thẻ chỉ hiện tên, giấu hẳn giá trị; bấm vào mới thấy trong hộp chi tiết.
   * Dùng cho thẻ đặt sát thiết bị trong tranh, nơi chỉ cần gọi tên cho người xem
   * biết đó là cái gì, còn trạng thái thì tra khi cần.
   */
  hideValues?: boolean
  /**
   * Đặt tâm thẻ trùng tâm khung thay vì neo mép trái trên.
   *
   * Thẻ thường rộng hơn khung vì tên không được xuống dòng, nên neo mép trái sẽ đẩy
   * chữ lệch sang phải so với chỗ đã canh. Nhãn ghim vào một thiết bị vẽ trong tranh
   * cần trùng tâm thì mới chỉ đúng vào nó. Thẻ canh giữa bỏ qua `anchor`.
   */
  centered?: boolean
  items: string[]
}

/** Công suất không có cảm biến riêng, tính từ điện áp nhân dòng điện. */
export const DERIVED_POWER = "POWER"

export const SCADA_METRICS: ScadaMetric[] = [
  { code: "WATER_TEMPERATURE", kind: "SENSOR", label: "Nhiệt độ nước" },
  { code: "PH", kind: "SENSOR", label: "Độ pH", fullLabel: "Độ pH (chua – kiềm)" },
  { code: "DO", kind: "SENSOR", label: "Oxy hòa tan", fullLabel: "Oxy hòa tan (DO)" },
  { code: "WATER_LEVELW2", kind: "SENSOR", label: "Mực nước", fullLabel: "Mực nước bể cá" },
  { code: "WATER_LEVEL", kind: "SENSOR", label: "Mực nước", fullLabel: "Mực nước bể lọc vi sinh" },
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
    box: { x: 31.29, y: 16.61, w: 14.02, h: 7.71 },
    anchor: "bottom",
    icon: "droplets",
    items: ["WATER_LEVEL", "TDS", "NO3", "NH3"],
  },
  {
    id: "biofilter-pump",
    title: "Bơm",
    // Tâm khung đặt trùng tâm bồn chứa (61,17% — lấy từ điểm cái bơm vẽ trong bồn).
    // Thẻ canh giữa nên tự co theo chữ rồi dịch lại nửa chính nó, không còn lệch trái
    // như khi neo mép trái với một khung rộng hơn nội dung.
    box: { x: 54.76, y: 12.66, w: 12.82, h: 8.3 },
    centered: true,
    icon: "waves",
    // Thẻ này thu về đúng cái bơm đặt dưới nó trong tranh. Van cấp nước đã có thẻ riêng
    // cạnh cái van thật, còn van xả đáy thì chưa được đánh dấu vị trí nên tạm chưa hiện.
    items: ["BIOFILTER_PUMP"],
  },
  {
    id: "fish-tank",
    title: "Bể cá",
    box: { x: 60.64, y: 70.61, w: 10.74, h: 18.51 },
    stacked: true,
    icon: "fish",
    // Bơm và máy sủi nằm ngay trong bể cá: đặt cạnh chỉ số oxy thì người xem đọc được
    // cả câu "DO bằng 0 mà máy sủi đang BẬT" thay vì phải sang màn hình khác đối chiếu.
    items: ["WATER_TEMPERATURE", "PH", "DO", "WATER_LEVELW2", "FISH_TANK_PUMP", "AERATION_PUMP"],
  },
  // Sáu đồng hồ trên tủ điện: nhãn đã vẽ sẵn trên tranh nên chỉ đổ số.
  {
    id: "meter-grid",
    title: null,
    box: { x: 78.26, y: 61.12, w: 6.42, h: 6.78 },
    valueOnly: true,
    items: ["VOLTAGE", "CURRENT"],
  },
  {
    id: "meter-power",
    title: null,
    box: { x: 89.16, y: 60.63, w: 5.69, h: 3.19 },
    valueOnly: true,
    items: [DERIVED_POWER],
  },
  // Bốn đồng hồ dưới đây chưa có cảm biến nào trong hệ thống, để trống thay vì bịa số.
  { id: "meter-solar", title: null, box: { x: 78.67, y: 75.42, w: 5.7, h: 1.87 }, valueOnly: true, items: [] },
  { id: "meter-battery", title: null, box: { x: 89.5, y: 75.56, w: 5.63, h: 3.29 }, valueOnly: true, items: [] },
  { id: "meter-ac", title: null, box: { x: 78.82, y: 86.29, w: 5.48, h: 2.82 }, valueOnly: true, items: [] },
  { id: "meter-dc", title: null, box: { x: 89.08, y: 86.29, w: 5.33, h: 2.58 }, valueOnly: true, items: [] },
  // Hai van đỏ vẽ rời trên tranh, mỗi cái một nhãn đặt ngay cạnh nó.
  // Trang hiệu chỉnh gọi chúng là card-100 và card-101 theo đúng thứ tự dưới đây.

  // Van ở bồn nước dưới bên trái: chính là Van điện từ cấp nước trong cơ sở dữ liệu.
  // Mặt thẻ chỉ gọi tên cho gọn, trạng thái BẬT/TẮT để trong hộp chi tiết.
  {
    id: "fresh-water-valve",
    title: "Van cấp nước",
    box: { x: 13.42, y: 59.01, w: 6.45, h: 5.55 },
    icon: "droplet",
    hideValues: true,
    centered: true,
    items: ["FRESH_WATER_VALVE"],
  },

  // Van trên đường ống cạnh bể lọc. Chưa có cơ cấu nào trong cơ sở dữ liệu ứng với nó
  // nên chỉ ghi tên tạm; khi nào đấu cảm biến vào thì điền items là thẻ tự có số.
  { id: "irrigation-valve", title: "Van tưới", box: { x: 45.62, y: 23.08, w: 5.65, h: 4.78 }, icon: "sprout", centered: true, items: [] },
]

/**
 * Thẻ tình trạng hệ thống, chiếm chỗ của thẻ chỉ số không khí trước đây.
 * Không gắn chỉ số nào: nó tổng hợp sức khoẻ toàn hệ thống và dẫn sang trang cảnh báo.
 */
export const SCADA_SYSTEM_CARD = {
  id: "system",
  // Chỉ x và y được dùng: thẻ tự co đúng bằng bề ngang dòng chữ dài nhất,
  // nên w và h giữ lại chỉ để ghi nhớ vùng đã dành cho nó lúc hiệu chỉnh.
  box: { x: 2.21, y: 2.17, w: 17.14, h: 13.46 },
} as const

/**
 * Cột đo mực nước bể cá, dựng dọc bên trái bể và cao đúng bằng bể.
 * Ảnh nền chỉ vẽ được hai mức 60% và 100%, nên cột này là chỗ duy nhất
 * thể hiện mực nước liên tục theo đúng số đo.
 */
export const SCADA_LEVEL_GAUGE = {
  code: "WATER_LEVELW2",
  box: { x: 54.33, y: 70.17, w: 2.17, h: 19.15 },
} as const

// Chưa hiển thị: AIR_TEMPERATURE, AIR_HUMIDITY, LIGHT_INTENSITY,
// FILTER_DRAIN_VALVE, GROW_LIGHT, WARNING_LIGHT, WARNING_BUZZER.
// Những chỉ số này chưa được đánh dấu vị trí trên tranh. Thêm vào items của một thẻ
// hoặc tạo thẻ mới cho chúng khi đã có toạ độ.
