# Aquaponics Platform

## Cài đặt

Yêu cầu: Docker và Docker Compose.

```bash
git clone https://github.com/CopyyQ/aquaponics-platform-plab.git
cd aquaponics-platform-plab
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Sửa các giá trị cần thiết trong `backend/.env`, đặc biệt `SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD` và `TELEGRAM_BOT_TOKEN` nếu sử dụng Telegram.

## Build và chạy

```bash
docker compose build
docker compose up -d
docker compose ps
```

Frontend: `http://localhost:3000`

Backend health: `http://localhost:8000/health`

## Dừng

```bash
docker compose down
```
