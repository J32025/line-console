import os
import sys

# ให้ import _lib.* ได้เหมือนตอนรันบน Vercel (api/ เป็น root ของ Python)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
