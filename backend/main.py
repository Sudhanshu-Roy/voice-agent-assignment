"""FastAPI entrypoint for the phone collection backend."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from backend.database import engine, Base
from backend.routes.phones import router as phones_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("vaiu.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")
    yield
    logger.info("Backend shutdown complete.")


app = FastAPI(
    title="Phone Collection API",
    description="Stores phone numbers collected by the LiveKit voice agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins = [
    frontend_url,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_msg = errors[0].get("msg") if errors else "Validation error"
    logger.warning(f"Validation error on {request.url.path}: {error_msg}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({
            "success": False,
            "message": error_msg,
            "errors": errors
        })
    )


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint required by assignment specification."""
    return {"status": "ok"}


# Include routes
app.include_router(phones_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
