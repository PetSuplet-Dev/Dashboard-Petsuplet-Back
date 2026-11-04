import os
import re
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import models
from app.api.api import api_router
from app.scheduler import setup_scheduler, scheduler

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: iniciar planificador de tareas en segundo plano
    try:
        task_scheduler = setup_scheduler()
        task_scheduler.start()
        logger.info("Planificador de tareas en segundo plano iniciado con éxito.")
    except Exception as e:
        logger.error(f"Error al iniciar el planificador de tareas: {e}", exc_info=True)
    yield
    # Shutdown: detener planificador de tareas de forma limpia
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Planificador de tareas detenido con éxito.")
    except Exception as e:
        logger.error(f"Error al detener el planificador de tareas: {e}", exc_info=True)


app = FastAPI(
    title="Automatization IA Backend",
    description="Backend modular para automatización y análisis financiero con IA",
    version="1.0.0",
    redirect_slashes=False,
    swagger_ui_parameters={"withCredentials": True},
    lifespan=lifespan,
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://petsuplet-frontend-765331002671.us-central1.run.app",
    "https://dev-ps-dashboard-frontend-765331002671.us-central1.run.app",
]

origin_regex = re.compile(
    r"^https://(petsuplet-frontend|dev-ps-dashboard-frontend).*\.run\.app$"
)

allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
allowed_headers = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https://(petsuplet-frontend|dev-ps-dashboard-frontend).*\.run\.app$",
    allow_credentials=True,
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
)

# Compresión GZip automática para respuestas superiores a 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Manejador global para asegurar cabeceras CORS en errores HTTP (ej. 401 Unauthorized, 404, etc.)
@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin")
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )
    if origin and (origin in origins or origin_regex.match(origin)):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)
        response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
    return response


# Incluir las rutas
app.include_router(api_router, prefix="/api")


@app.get("/")
def read_root():
    return {"message": "Automatization IA API is running successfully!"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
