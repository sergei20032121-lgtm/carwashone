from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.database import Base, engine, ensure_compatible_schema
from app.routers import auth, services, bookings, dry_cleaning, schedule, reviews, admin, walk_in, vk, client, public_stats, payments, finances, phone_gateway

Base.metadata.create_all(bind=engine)
ensure_compatible_schema()
PROJECT_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title=settings.app_name,
    description="REST API автомойки: запись по телефону, химчистка отдельным разделом, "
                "личный кабинет с бонусами, график сотрудников, интеграция с 2ГИС.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
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
app.include_router(client.router)
app.include_router(public_stats.router)
app.include_router(payments.router)
app.include_router(finances.router)
app.include_router(phone_gateway.router)

app.mount("/static", StaticFiles(directory=PROJECT_DIR / "app" / "static"), name="static")
app.mount("/site", StaticFiles(directory=PROJECT_DIR / "frontend", html=True), name="site")


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": settings.app_name, "site": "/site/", "docs": "/docs"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin.html\n"
        "Disallow: /manager.html\n"
        "Disallow: /master.html\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        "Sitemap: https://carwashone.ru/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    urls = ["", "cabinet.html", "privacy.html", "consent.html"]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for path_part in urls:
        loc = f"https://carwashone.ru/site/{path_part}" if path_part else "https://carwashone.ru/"
        body += f"  <url><loc>{loc}</loc></url>\n"
    body += "</urlset>\n"
    return Response(content=body, media_type="application/xml")
