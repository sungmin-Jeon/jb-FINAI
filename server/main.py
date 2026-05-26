# server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers.compliance import router as compliance_router

app = FastAPI(
    title="준법자문 AI 에이전트",
    description="금융소비자보호법 기반 준법심사 자동화 시스템",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(compliance_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "준법자문 AI 에이전트 API is running",
    }