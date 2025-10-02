"""Health check endpoints for Code Review Assistant."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "Service is running"}


@router.get("/health/db")
async def db_health_check(db: AsyncSession = Depends(get_db)):
    """Database health check endpoint."""
    try:
        # Simple query to check database connection
        result = await db.execute("SELECT 1")
        if result:
            return {"status": "ok", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "error", "message": f"Database connection failed: {str(e)}"}