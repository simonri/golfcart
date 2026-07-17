from fastapi import APIRouter

from api.readings.endpoints import router as readings_router
from api.tasks.endpoints import router as tasks_router

router = APIRouter(prefix="/v1")

router.include_router(tasks_router)
router.include_router(readings_router)
