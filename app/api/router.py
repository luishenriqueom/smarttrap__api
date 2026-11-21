from fastapi import APIRouter

from app.api.routes import auth, captures, devices, firmware, ingest, metrics, models, species, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(devices.router)
api_router.include_router(captures.router)
api_router.include_router(metrics.router)
api_router.include_router(ingest.router)
api_router.include_router(species.router)
api_router.include_router(models.router)
api_router.include_router(firmware.router)
