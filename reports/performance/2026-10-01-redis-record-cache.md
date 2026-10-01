# Báo cáo triển khai và kiểm thử hiệu năng Redis Record Cache

**Ngày thực hiện:** 2026-10-01

**Máy chủ:** `192.168.1.182`

**Thư mục triển khai trên server:** `/home/plab/Desktop/Nguyen_Anh_Quyet_PLAB/Aquaponics_PLAB`

**Nhánh tính năng:** `feat/backend-redis-cache`

**Commit triển khai Redis:** `11e11fe` — `feat(backend): add fail-open Redis record cache`

**Commit công cụ kiểm thử hiệu năng:** `5966c99` — `test(perf): add bounded catalog read load driver`

**Commit merge triển khai trên server:** `349c2bb` — `deploy: merge redis record cache`

## 1. Phạm vi

Báo cáo này kiểm tra Redis cache cho các API đọc chi tiết danh mục ổn định của Backend:

- `SensorModel`
- `ActuatorModel`
- `DeviceTemplate`
- `ScenarioCatalog`

PostgreSQL vẫn là **nguồn dữ liệu chuẩn (source of truth)**. Redis chỉ đóng vai trò cache có thể xóa và dựng lại bất kỳ lúc nào.

Thiết kế cache theo cơ chế **cache-aside** và **fail-open**:

1. Backend thử đọc dữ liệu từ Redis.
2. Nếu cache hit, trả kết quả trực tiếp từ Redis.
3. Nếu cache miss, đọc dữ liệu từ PostgreSQL rồi ghi vào Redis với TTL.
4. Nếu Redis lỗi hoặc mất kết nối, API vẫn tiếp tục đọc từ PostgreSQL thay vì trả lỗi.

Công cụ benchmark được thêm tại:

`backend/scripts/load_read_endpoints.py`

Test hợp đồng của công cụ benchmark:

`backend/unit_tests/test_load_read_script_contract.py`

Công cụ benchmark chỉ gửi request `GET`, lấy Bearer Token từ biến môi trường, không in token ra log, có giới hạn concurrency/RPS/thời gian chạy và xuất các chỉ số p50/p95/p99.

## 2. Trạng thái triển khai trên server

Sau khi triển khai, trạng thái cuối cùng:

- Backend: **healthy**
- API Gateway: **healthy**
- Frontend: **HTTP 200**
- Redis: **healthy**, trả `PONG`
- PostgreSQL: **healthy**
- MQTT Consumer: **running**
- Scheduler: **running**
- MQTT Broker: **running**

Cấu hình Redis đang chạy:

| Tham số | Giá trị |
|---|---:|
| Image | `redis:7-alpine` |
| Public cổng 6379 ra host | **Không** |
| `maxmemory` | 256 MiB |
| `maxmemory-policy` | `allkeys-lru` |
| AOF | Tắt |
| RDB save | Tắt |
| TTL cache của Backend | 60 giây |
| Redis socket timeout | 0,5 giây |

Redis chỉ được truy cập trong Docker network, không expose cổng `6379` ra LAN/Internet.

Redis không làm thay đổi schema hay dữ liệu PostgreSQL. Revision database sau triển khai vẫn giữ nguyên:

`v2_automatic_feeder`

## 3. Kiểm thử chức năng trên server

Chạy trực tiếp các unit test liên quan đến Redis cache và công cụ benchmark trên container Backend:

```text
..........                                                               [100%]
10 passed in 0.39s
```

Kết quả:

- Redis cache test: **PASS**
- Cache hit/cache miss: **PASS**
- TTL: **PASS**
- Invalidation: **PASS**
- Redis unavailable fallback: **PASS**
- Performance load-driver contract: **PASS**

## 4. Phương pháp benchmark

Endpoint dùng để đo:

`GET /api/v1/sensor-models/1`

Luồng request:

`load driver trong Backend container -> API Gateway (Nginx) -> Backend -> Redis/PostgreSQL`

Cách đo này tập trung vào hiệu năng xử lý phía server và loại bỏ độ trễ từ máy Windows/LAN.

Tất cả request benchmark:

- có xác thực Bearer Token;
- chỉ dùng `GET`;
- không sửa dữ liệu;
- không gọi API tạo/xóa/cập nhật.

Baseline được đo **ngay trước khi bật Redis** trên cùng server và cùng endpoint.

## 5. Kết quả trước và sau Redis ở mức 20 request/giây

Cấu hình:

- Thời gian: 5 giây
- Mục tiêu: 20 request/giây
- Concurrency: 10
- Tổng request: 100

| Chỉ số | Trước Redis | Sau Redis | Mức cải thiện |
|---|---:|---:|---:|
| Thành công | 100/100 | 100/100 | Không lỗi |
| Throughput | 10,66 req/s | 20,12 req/s | **+88,72% / 1,89 lần** |
| Latency trung bình | 819,13 ms | 20,49 ms | **giảm 97,50% / nhanh hơn 39,97 lần** |
| p50 | 673,79 ms | 18,14 ms | **giảm 97,31% / nhanh hơn 37,15 lần** |
| p95 | 2104,05 ms | 23,87 ms | **giảm 98,87% / nhanh hơn 88,14 lần** |
| p99 | 2127,96 ms | 84,93 ms | **giảm 96,01% / nhanh hơn 25,06 lần** |
| Max | 2140,15 ms | 157,46 ms | **giảm 92,64%** |

Thống kê Redis sau bài test:

```text
keyspace_hits:102
keyspace_misses:1
DBSIZE: 1
```

Tỷ lệ cache hit quan sát được xấp xỉ:

**99,03%**

## 6. Kết quả trước và sau Redis ở mức 50 request/giây

Cấu hình:

- Thời gian: 5 giây
- Mục tiêu: 50 request/giây
- Concurrency: 20
- Tổng request: 250

| Chỉ số | Trước Redis | Sau Redis ổn định | Mức cải thiện |
|---|---:|---:|---:|
| Thành công | 250/250 | 250/250 | Không lỗi |
| Throughput | 18,97 req/s | 50,03 req/s | **+163,73% / 2,64 lần** |
| Latency trung bình | 986,64 ms | 16,01 ms | **giảm 98,38% / nhanh hơn 61,63 lần** |
| p50 | 893,73 ms | 16,32 ms | **giảm 98,17% / nhanh hơn 54,75 lần** |
| p95 | 1700,18 ms | 17,59 ms | **giảm 98,97% / nhanh hơn 96,64 lần** |
| p99 | 2372,71 ms | 18,46 ms | **giảm 99,22% / nhanh hơn 128,51 lần** |
| Max | 2490,31 ms | 19,28 ms | **giảm 99,23%** |

Thống kê Redis:

```text
keyspace_hits:254
keyspace_misses:1
```

Tỷ lệ cache hit xấp xỉ:

**99,61%**

### Hiện tượng warm-up ngay sau khi recreate container

Lần chạy đầu tiên ngay sau khi Backend vừa được recreate vẫn đạt đủ khoảng 50 request/giây, nhưng tail latency còn cao tạm thời:

- p50: 18,87 ms
- p95: 650,62 ms
- p99: 782,12 ms

Sau khi service ổn định và chạy lại cùng cấu hình:

- p50: 16,32 ms
- p95: 17,59 ms
- p99: 18,46 ms

Điều này cho thấy độ trễ cao ở lần đầu là hiện tượng warm-up sau deploy, không phải trạng thái ổn định của hệ thống.

## 7. Stress test 100 request/giây

Cấu hình:

- Thời gian: 5 giây
- Mục tiêu: 100 request/giây
- Concurrency: 40
- Tổng request: 500

Kết quả:

| Chỉ số | Kết quả |
|---|---:|
| Thành công | **500/500** |
| HTTP error | **0** |
| Transport error | **0** |
| Throughput | **99,94 req/s** |
| Latency trung bình | 12,99 ms |
| p50 | 12,79 ms |
| p95 | 17,25 ms |
| p99 | 27,72 ms |
| Max | 37,16 ms |

Thống kê Redis:

```text
keyspace_hits:505
keyspace_misses:0
```

Tỷ lệ cache hit trong lượt chạy warm này:

**100%**

Ở mức 100 request/giây, hệ thống vẫn đáp ứng gần đúng target và không xuất hiện lỗi HTTP/transport.

## 8. Kiểm thử Redis bị mất kết nối

Redis được chủ động stop trong khi Backend vẫn tiếp tục chạy.

Sau đó gửi 5 request đọc chi tiết SensorModel.

Kết quả:

```text
redis_down_statuses=200,200,200,200,200
redis_down_latency_ms_mean=50.873
redis_down_latency_ms_max=116.698
```

Kết luận:

**5/5 request vẫn HTTP 200 thông qua PostgreSQL fallback.**

Sau đó Redis được khởi động lại:

```text
redis_restarted=PONG
/health -> {"status":"ok"}
```

Điều này xác nhận cơ chế **fail-open hoạt động đúng**:

- Redis mất kết nối không làm API catalog bị down.
- Hệ thống chỉ bị tăng latency tạm thời do phải đọc từ PostgreSQL.
- Khi Redis trở lại, Backend tiếp tục sử dụng cache bình thường.

## 9. Vấn đề phát hiện trong quá trình deploy

Khi Backend container được recreate, Nginx API Gateway đang chạy giữ lại địa chỉ IP cũ của Backend container.

Khi đó:

- Backend mới đã healthy;
- nhưng API Gateway vẫn gọi IP cũ;
- kết quả tạm thời trả `502 Bad Gateway`.

Sau khi restart `api_gateway`, Nginx resolve lại Backend service và hệ thống trở lại bình thường:

- API Gateway: healthy
- `/health`: HTTP 200
- Frontend: HTTP 200

Đây không phải lỗi của Redis cache, nhưng là điểm cần lưu ý trong quy trình deploy.

### Khuyến nghị vận hành

Sau khi recreate Backend container, nên thực hiện một trong hai phương án:

1. restart/recreate `api_gateway`; hoặc
2. cải tiến Nginx để resolve Docker DNS động thay vì giữ IP Backend cũ.

## 10. Tổng kết

Redis Record Cache đã được triển khai thành công trên server và hoạt động ổn định.

Kết quả chính:

- PostgreSQL vẫn là nguồn dữ liệu chuẩn.
- Redis chỉ đóng vai trò cache.
- Redis không public cổng `6379`.
- Cache hit thực tế đạt khoảng **99–100%**.
- Ở 20 req/s, p95 giảm từ **2104 ms xuống 23,87 ms**.
- Ở 50 req/s, p95 giảm từ **1700 ms xuống 17,59 ms**.
- Throughput 50 req/s tăng từ **18,97 lên 50,03 req/s**.
- Stress test 100 req/s đạt **500/500 request thành công**.
- p95 ở 100 req/s chỉ **17,25 ms**.
- Redis down vẫn có **5/5 request HTTP 200** nhờ PostgreSQL fallback.
- Unit test trực tiếp trên server: **10 test PASS**.
- Backend, API Gateway, Frontend, Redis và PostgreSQL đều healthy sau kiểm thử.

## 11. Kết luận

Redis cache mang lại cải thiện hiệu năng rõ rệt cho các API đọc chi tiết catalog.

Trong trạng thái ổn định:

- latency giảm mạnh;
- throughput tăng;
- tải đọc PostgreSQL được giảm;
- Redis không trở thành single point of failure;
- hệ thống vẫn phục vụ được request khi Redis bị dừng.

Với phạm vi hiện tại, Redis Record Cache **đủ điều kiện tiếp tục bật trên môi trường server** cho các API catalog detail đã triển khai.
