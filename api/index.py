"""
LINE Console API — FastAPI บน Vercel Python runtime
ทุก endpoint (ยกเว้น /api/webhook, /api/health) ต้องมี  Authorization: Bearer <LIFF id_token>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LINE Console API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# routes แยกเป็นกลุ่มอยู่ใน _lib/routers/ (helper ร่วมอยู่ใน _lib/core.py)
# ลำดับ include = ลำดับจับคู่ path (เหมือนเดิมก่อนแยกไฟล์)
from _lib.routers.system import router as system_router  # noqa: E402
from _lib.routers.cron import router as cron_router  # noqa: E402
from _lib.routers.webhook import router as webhook_router  # noqa: E402
from _lib.routers.richmenu import router as richmenu_router  # noqa: E402
from _lib.routers.users import router as users_router  # noqa: E402
from _lib.routers.messaging import router as messaging_router  # noqa: E402
from _lib.routers.autoreply import router as autoreply_router  # noqa: E402
from _lib.routers.stats import router as stats_router  # noqa: E402
from _lib.routers.billing import router as billing_router  # noqa: E402
from _lib.routers.classes import router as classes_router  # noqa: E402

app.include_router(system_router)
app.include_router(cron_router)
app.include_router(webhook_router)
app.include_router(richmenu_router)
app.include_router(users_router)
app.include_router(messaging_router)
app.include_router(autoreply_router)
app.include_router(stats_router)
app.include_router(billing_router)
app.include_router(classes_router)
