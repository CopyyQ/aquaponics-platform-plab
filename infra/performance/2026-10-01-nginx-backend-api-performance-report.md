# Báo cáo kiểm tra hiệu năng Nginx Backend API

**Ngày kiểm tra:** 2026-10-01
**Endpoint:** `GET /health`

## 1. Cấu hình test

Các bài test chính:

| Bài test | Tổng request | Concurrency |
|---|---:|---:|
| Benchmark cơ bản | 1.000 | 25 |
| Stress test | 100.000 | 100 |
| Stress test dài | 1.000.000 | 100 |

Ngưỡng đánh giá cho bài stress lớn:

- Error rate: **<= 0,1%**
- p95: **<= 300 ms**
- p99: **<= 750 ms**
- Throughput: **>= 100 req/s**

## 2. Kết quả benchmark cơ bản

Chạy 3 lần, mỗi lần 1.000 request với concurrency 25:

| Run | Thành công | Lỗi | Throughput | p95 | p99 |
|---:|---:|---:|---:|---:|---:|
| 1 | 1.000/1.000 | 0% | 978,06 req/s | 29,01 ms | 37,49 ms |
| 2 | 1.000/1.000 | 0% | 1.017,58 req/s | 28,22 ms | 30,74 ms |
| 3 | 1.000/1.000 | 0% | 1.037,73 req/s | 25,47 ms | 27,05 ms |

**Kết quả:** PASS.

## 3. Stress test 100.000 request

### Trước khi tối ưu Nginx

Với 100.000 request và concurrency 100:

| Metric | Kết quả |
|---|---:|
| Thành công | 37.237 |
| Thất bại | 62.763 |
| Error rate | **62,763%** |
| Throughput | 1.249,30 req/s |

Nguyên nhân là Nginx tạo quá nhiều kết nối mới tới FastAPI, dẫn tới cạn ephemeral port và trả nhiều lỗi 502.

### Sau khi bật upstream keep-alive

Cấu hình Nginx được tối ưu để tái sử dụng kết nối tới FastAPI.

Kết quả chạy lại:

| Metric | Kết quả |
|---|---:|
| Thành công | **100.000 / 100.000** |
| Thất bại | **0** |
| Error rate | **0%** |
| Throughput | **1.226,66 req/s** |
| Mean latency | 81,43 ms |
| p95 | **100,60 ms** |
| p99 | **106,58 ms** |

**Kết quả:** PASS.

## 4. Stress test 1.000.000 request

Bài test cuối chạy trên stack Docker cô lập, sử dụng đúng backend image và cấu hình Nginx đã tối ưu.

| Metric | Kết quả |
|---|---:|
| Tổng request | **1.000.000** |
| Thành công | **1.000.000** |
| Thất bại | **0** |
| Error rate | **0%** |
| Thời gian | **782,34 giây** |
| Throughput | **1.278,21 req/s** |
| Mean latency | **78,20 ms** |
| p50 | **78,32 ms** |
| p95 | **96,87 ms** |
| p99 | **102,43 ms** |
| Max | 2.069,22 ms |

**Kết quả:** PASS.

## 5. Kết luận

Sau khi bật upstream keep-alive cho Nginx:

- Hệ thống xử lý **1.000.000 request liên tục** với concurrency 100.
- **0 request lỗi**.
- Throughput ổn định khoảng **1.200–1.300 req/s**.
- p95 khoảng **97–101 ms** ở tải cao.
- Nginx không còn là bottleneck chính.
- Giới hạn tiếp theo nằm ở FastAPI single worker khi CPU đạt gần 100% một core.

Kết luận chung: **Nginx Backend API đạt yêu cầu hiệu năng của bài test hiện tại.**
