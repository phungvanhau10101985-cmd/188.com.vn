This is a [Next.js](https://nextjs.org) project (188.com.vn storefront + admin).

**Cài đặt đầy đủ (backend + frontend + cổng, Playwright, Windows `dev-clear-start.bat`):** xem **[HUONG_DAN_CAI_DAT.md](../HUONG_DAN_CAI_DAT.md)** ở thư mục gốc repo.

## Chạy dev (frontend)

Đảm bảo API FastAPI đã chạy (mặc định **http://127.0.0.1:8001**). Trong thư mục `frontend/`:

```bash
npm install
npm run dev
```

Lệnh `dev` ép cổng **3001** (`scripts/next-dev.cjs`). Mở [http://localhost:3001](http://localhost:3001).

Tùy chọn: `cp .env.local.example .env.local` (Windows: `copy`) — xem mẫu cho `API_INTERNAL_ORIGIN` / ngrok.

## Generic Next.js

```bash
npm run dev
# or yarn dev / pnpm dev / bun dev
```

Chỉnh `app/page.tsx` — trang tự reload khi sửa.

Dự án dùng [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) để tối ưu font.

## Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [Learn Next.js](https://nextjs.org/learn)
- [Next.js GitHub](https://github.com/vercel/next.js)

## Deploy on Vercel

Xem [Next.js deploying](https://nextjs.org/docs/app/building-your-application/deploying). **Production 188.com.vn** thường dùng VPS + Nginx — [HUONG_DAN_DEPLOY.md](../HUONG_DAN_DEPLOY.md).
