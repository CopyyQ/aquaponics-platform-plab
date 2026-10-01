# Báo cáo triển khai và kiểm tra hiệu năng Nginx Backend API

**Ngày kiểm tra:** 2026-10-01
**Máy chủ:** PLAB `192.168.1.182`
**Deployment:** `aquaponics-plab-final`
**Frontend:** `http://192.168.1.182:3100`
**Backend API Gateway:** `http://192.168.1.182:8100`

## 1. Kết luận

Đầu việc **Thêm Nginx tầng API Backend** đã được triển khai lên server và vượt qua các gate chức năng lẫn hiệu năng được định nghĩa cho bài test này.

- Nginx API gateway: **PASS**
- Backend health qua Nginx: **HTTP 200**
- Nginx config `nginx -t`: **PASS**
- Docker Compose config: **PASS**
- Infrastructure regression tests: **3/3 PASS**
- Performance gate, 3 lần chạy: **3/3 PASS**
- Playwright smoke: **3/3 PASS**
- Lỗi request ở Playwright: **0**
- Backend container không còn publish trực tiếp port 8000 ra host.
- Host port `8100` hiện do `api_gateway` Nginx sở hữu.

## 2. Kiến trúc sau triển khai

Luồng backend trên host:

```text
Client
  |
  | :8100
  v
Nginx api_gateway :80
  |
  | Docker network
  v
FastAPI backend :8000
```

Các cổng deployment giữ nguyên:

| Thành phần | Port host | Trạng thái |
|---|---:|---|
| Frontend | 3100 | Giữ nguyên |
| Backend API qua Nginx | 8100 | Đã chuyển sang Nginx |
| MQTT | 1884 | Giữ nguyên |
| FastAPI backend | Không publish host | Chỉ còn internal `:8000` |

Caddy/public frontend hiện tại không bị thay đổi. Task này không sửa Frontend và không thay đổi đường proxy nội bộ của frontend.

## 3. Thay đổi đã triển khai

Nguồn GitHub:

- Branch: `feat/nginx-backend-api`
- Nginx implementation: `b6b7b48`
- Performance benchmark: `baac956`

Server đã cherry-pick thành:

- `3082e4d feat(infra): add nginx backend api gateway`
- `35f4301 test(infra): add backend gateway performance benchmark`

Server có backup branch trước deployment:

- `deploy-backup/nginx-backend-api-20261001-084439`

File deployment local `docker-compose.deploy.yml` được giữ dạng server-local/untracked và đã được backup trước khi chỉnh. Không xóa PostgreSQL volume, MQTT volume hay dữ liệu retained.

## 4. Validation chức năng trên server

### 4.1 Backend health qua Nginx

```text
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json

{"status":"ok"}
```

Điều này xác nhận request `:8100/health` thực sự đi qua Nginx trước khi tới FastAPI.

### 4.2 Container/port

Sau deployment:

```text
api_gateway  -> 0.0.0.0:8100->80/tcp   healthy
backend      -> 8000/tcp                healthy
frontend     -> 0.0.0.0:3100->80/tcp   healthy
postgres     -> 5432/tcp                healthy
mqtt         -> 0.0.0.0:1884->1883/tcp
```

`docker port aquaponics-plab-final-backend-1` không trả published port; backend không còn expose trực tiếp ra host.

### 4.3 Regression tests

Lệnh:

```bash
python3 -m unittest discover -s infra/tests -p 'test_nginx_backend_api.py' -v
docker exec aquaponics-plab-final-api_gateway-1 nginx -t
docker compose -f docker-compose.yml -f docker-compose.deploy.yml -f docker-compose.public.yml config --quiet
```

Kết quả:

```text
Ran 3 tests
OK

nginx: configuration file /etc/nginx/nginx.conf test is successful
```

## 5. Môi trường benchmark

| Thuộc tính | Giá trị |
|---|---|
| CPU | 2 x Intel Xeon E5-2686 v4 @ 2.30 GHz |
| Logical CPUs | 72 |
| RAM | 62 GiB |
| RAM available lúc đo | khoảng 57 GiB |
| Kernel | Linux 6.8.0-138-generic x86_64 |
| Docker Engine | 29.7.2 |
| Load average lúc hậu kiểm | 0.53 / 0.62 / 0.60 |

Benchmark dùng Python standard library, HTTP keep-alive, endpoint read-only `GET /health`.

Acceptance gate:

- Requests: **1000/run**
- Concurrency: **25**
- Warm-up: **25**
- Error rate tối đa: **0%**
- p95 tối đa: **100 ms**
- p99 tối đa: **250 ms**
- Throughput tối thiểu: **100 req/s**

## 6. Kết quả benchmark từ host qua port 8100

Target:

```text
http://127.0.0.1:8100/health
Host -> Nginx -> FastAPI
```

| Run | Success | Error | RPS | Mean | p50 | p95 | p99 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1000/1000 | 0% | 978.06 | 25.05 ms | 24.30 ms | 29.01 ms | 37.49 ms | 37.65 ms |
| 2 | 1000/1000 | 0% | 1017.58 | 23.98 ms | 23.31 ms | 28.22 ms | 30.74 ms | 30.91 ms |
| 3 | 1000/1000 | 0% | 1037.73 | 23.48 ms | 23.83 ms | 25.47 ms | 27.05 ms | 27.83 ms |

**Median 3 runs:**

- Throughput: **1017.58 req/s**
- Mean latency: **23.98 ms**
- p50: **23.83 ms**
- p95: **28.22 ms**
- p99: **30.74 ms**
- Error rate: **0%**

Tất cả 3 lần chạy đều trả `PERFORMANCE_GATE=PASS`.

## 7. So sánh direct FastAPI và qua Nginx trong cùng Docker network

Cùng chạy từ backend container để giảm khác biệt phía client.

| Path | RPS | Mean | p50 | p95 | p99 | Error |
|---|---:|---:|---:|---:|---:|---:|
| Direct FastAPI `127.0.0.1:8000` | 1163.60 | 21.13 ms | 20.42 ms | 26.02 ms | 68.76 ms | 0% |
| Qua Nginx `api_gateway:80` | 973.73 | 25.15 ms | 24.06 ms | 30.52 ms | 33.94 ms | 0% |

Ở lần đo này, Nginx làm throughput giảm khoảng **16.3%**, mean latency tăng khoảng **19.0%**, và p95 tăng khoảng **17.3%** so với gọi loopback FastAPI trực tiếp. Đây là chi phí proxy trong bài test nhỏ này; cả hai đường đều vượt xa acceptance gate 100 req/s và p95 100 ms.

Không nên suy diễn p99 của hai mẫu đơn lẻ thành lợi thế của Nginx vì direct run có một số outlier lớn hơn.

## 8. Playwright smoke sau deployment

```text
Playwright E2E: PASS
Target: http://192.168.1.182:3100
Backend: http://192.168.1.182:8100
Checks: 3/3
Browser errors: 1
Failed requests: 0
```

Ba check đã pass:

1. Backend `/health` trả 200 và body chứa `ok`.
2. Frontend trả HTTP 200.
3. DOM render thành công.

Console có một HTTP 401 tại:

```text
/api/v1/auth/refresh
```

Đây là request refresh session khi browser smoke chưa đăng nhập; không phải transport failure và không làm smoke gate thất bại. Playwright ghi nhận **0 failed network requests**.

## 9. File benchmark tái sử dụng

```text
infra/performance/backend_api_gateway_benchmark.py
```

Ví dụ chạy lại:

```bash
python3 infra/performance/backend_api_gateway_benchmark.py \
  --url http://127.0.0.1:8100/health \
  --requests 1000 \
  --concurrency 25 \
  --warmup 25 \
  --max-error-rate 0 \
  --max-p95-ms 100 \
  --max-p99-ms 250 \
  --min-rps 100
```

Script exit code khác 0 nếu bất kỳ performance gate nào không đạt.

## 10. Giới hạn của phép đo

Kết quả trên chứng minh hiệu năng của **Nginx gateway + FastAPI health path** trong LAN/server-local, không phải capacity planning cuối cùng cho toàn bộ hệ thống.

Chưa được suy rộng trực tiếp sang:

- API có truy vấn PostgreSQL nặng;
- API trả payload telemetry lớn;
- login/auth có Argon2;
- MQTT/control actuator;
- WAN/TLS qua public domain;
- soak test kéo dài hàng giờ;
- saturation test tới điểm CPU/worker cạn.

Nếu cần release performance gate sâu hơn, bước tiếp theo nên benchmark một nhóm read API thực tế với dữ liệu gần production và chạy load theo các mức concurrency 25/50/100 trong một database disposable hoặc read-only workload.


## 11. Stress test 100.000 request và root cause 502

Sau benchmark ban đầu, tải được tăng lên:

- Requests: **100.000**
- Concurrency: **100**

Cấu hình Nginx ban đầu chưa reuse upstream TCP connection. Kết quả:

| Metric | Kết quả |
|---|---:|
| Success | 37.237 |
| Failed | 62.763 |
| Error rate | **62,763%** |
| RPS | 1.249,30 |
| p95 | 125,18 ms |
| p99 | 168,47 ms |

Phần lớn lỗi là HTTP **502 Bad Gateway**.

Nginx error log xác nhận nguyên nhân:

```text
connect() to 192.168.32.4:8000 failed (99: Address not available)
while connecting to upstream
```

Tại thời điểm đó Nginx container có local ephemeral port range:

```text
32768 60999
```

Nginx đang mở connection mới tới FastAPI cho lượng lớn request liên tục, làm cạn ephemeral source ports trong thời gian TCP connection chưa được tái sử dụng.

### Fix

Đã đổi Nginx sang named upstream và bật connection reuse:

```nginx
upstream backend_api {
  server backend:8000;
  keepalive 256;
}

location / {
  proxy_pass http://backend_api;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
}
```

Regression test được bổ sung để khóa cấu hình này.

Commit fix trên branch:

```text
b1c3964 fix(infra): reuse nginx upstream connections
```

## 12. Re-test 100.000 request sau keep-alive fix

Cùng tải:

- Requests: **100.000**
- Concurrency: **100**
- Target production: `http://127.0.0.1:8100/health`

Kết quả:

| Metric | Kết quả |
|---|---:|
| Success | **100.000 / 100.000** |
| Failed | **0** |
| Error rate | **0%** |
| Elapsed | 81,52 s |
| Throughput | **1.226,66 req/s** |
| Mean | 81,43 ms |
| p50 | 81,05 ms |
| p95 | **100,60 ms** |
| p99 | **106,58 ms** |
| Max | 2.186,52 ms |

Kết quả: **PERFORMANCE_GATE=PASS**.

Trong giai đoạn tải ổn định, quan sát container:

- FastAPI backend: khoảng **101% CPU**, tương đương gần một CPU core bị sử dụng hết.
- Nginx API gateway: khoảng **42–47% CPU**.
- Memory backend khoảng **103 MiB**.
- Memory Nginx khoảng **56–59 MiB**.

Điều này cho thấy sau khi giải quyết connection reuse, bottleneck tiếp theo của health-path ở tải này là **single FastAPI worker / một CPU core**, không phải Nginx.

## 13. Stress test 1.000.000 request

Để tránh nhiễu từ các phiên deploy khác đang đồng thời thao tác production stack, bài 1M cuối được chạy trên **Docker stack cô lập trên cùng server**, dùng:

- chính image `aquaponics-plab-final-backend`;
- chính `infra/nginx/backend-api.conf` đã deploy;
- FastAPI **1 worker**, giống topology backend hiện tại;
- network Docker riêng;
- port test tạm `18100`;
- endpoint read-only `GET /health`.

Production `3100/8100/1884` không được dùng làm load target trong bài cuối này.

### Cấu hình

- Requests: **1.000.000**
- Concurrency: **100**
- Warm-up: **500**
- Request timeout: **3 s**
- Maximum accepted error rate: **0,1%**
- p95 gate: **300 ms**
- p99 gate: **750 ms**

### Kết quả

| Metric | Kết quả |
|---|---:|
| Success | **1.000.000 / 1.000.000** |
| Failed | **0** |
| Error rate | **0,000%** |
| Elapsed | **782,34 s** (~13 phút 02 giây) |
| Throughput | **1.278,21 req/s** |
| Mean | **78,20 ms** |
| p50 | **78,32 ms** |
| p95 | **96,87 ms** |
| p99 | **102,43 ms** |
| Max | **2.069,22 ms** |

Kết quả cuối:

```text
PERFORMANCE_GATE=PASS
```

Trong bài 1M:

- isolated FastAPI backend duy trì xấp xỉ **100–101% CPU**;
- isolated Nginx dao động khoảng **28–31% CPU** ở các mẫu quan sát;
- endpoint stress liên tục trả 200;
- production `:8100/health` được kiểm tra song song vẫn trả **200**;
- sau test, toàn bộ stress containers/network tạm đã được xóa;
- production backend và API gateway đều trở lại/duy trì trạng thái **healthy**.

### Kết luận stress test

Sau keep-alive fix, hệ thống đã chịu được **1 triệu request liên tục với concurrency 100 mà không có request lỗi** trên health path.

Giới hạn thấy rõ hiện tại không nằm ở Nginx. FastAPI một worker đã sử dụng gần trọn một CPU core ở mức khoảng **1,2–1,3k req/s**. Nếu mục tiêu tiếp theo là tăng throughput đáng kể thay vì chỉ chứng minh độ bền, cần benchmark worker scaling (ví dụ nhiều Uvicorn/Gunicorn workers) và sau đó chuyển sang API có PostgreSQL/telemetry để đo bottleneck thực tế.
