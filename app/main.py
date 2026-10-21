import os
import re
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# 1. CREAR LA APP INMEDIATAMENTE
app = FastAPI(
    title="Automatization IA Backend",
    description="Backend modular para automatización y análisis financiero con IA",
    version="1.0.0",
    redirect_slashes=False,
    swagger_ui_parameters={"withCredentials": True},
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


# 2. IMPORTACIONES LUEGO DE CREAR LA APP
from app import models
from app.api.api import api_router
from app.scheduler import setup_scheduler

# Incluir las rutas
app.include_router(api_router, prefix="/api")


@app.get("/")
def read_root():
    return {"message": "Automatization IA API is running successfully!"}


# 3. MANEJO DE EVENTOS DE ARRANQUE Y PARADA
@app.on_event("startup")
def on_startup():
    # Iniciar el planificador de tareas
    try:
        scheduler = setup_scheduler()
        scheduler.start()
        print("Planificador de tareas en segundo plano iniciado con éxito.")
    except Exception as e:
        print(f"Error al iniciar el planificador de tareas: {e}")


@app.on_event("shutdown")
def on_shutdown():
    # Detener el planificador de tareas
    try:
        from app.scheduler import scheduler

        if scheduler.running:
            scheduler.shutdown()
            print("Planificador de tareas detenido con éxito.")
    except Exception as e:
        print(f"Error al detener el planificador de tareas: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
