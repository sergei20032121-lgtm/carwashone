from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routers import auth, services, bookings, dry_cleaning, schedule, reviews, admin, walk_in, vk

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="REST API автомойки: запись по телефону, химчистка отдельным разделом, "
                "личный кабинет с бонусами, график сотрудников, интеграция с 2ГИС.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # сузить до реального домена сайта перед продакшеном
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(services.router)
app.include_router(bookings.router)
app.include_router(dry_cleaning.router)
app.include_router(schedule.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(walk_in.router)
app.include_router(vk.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/site", StaticFiles(directory="frontend", html=True), name="site")


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.app_name, "site": "/site/", "docs": "/docs"}
