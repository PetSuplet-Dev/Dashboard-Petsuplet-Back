FROM python:3.12-slim

# Usamos /src para que no choque con tu carpeta interna /app
WORKDIR /src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo tu proyecto dentro de /src
COPY . .

# Ahora la ruta "app.main:app" funcionará perfectamente en la raíz de /src
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]