"""FastAPI application entrypoint."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from app.routers import reservations, views

load_dotenv()

app = FastAPI(title="Meeting Room Booking")

app.include_router(views.router)
app.include_router(reservations.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
