# Imagen del servidor para un alojamiento fijo (Fly.io). Ver "Alojamiento fijo" en el README.
#
# Dos etapas: la web (React + Vite) se compila con Node y solo el resultado pasa a la imagen
# final, que sigue siendo Python puro, sin dependencias y sin Node.

# --- Etapa 1: compilar la web. Vite escribe en ../site, o sea /build/site. ---
FROM node:24-slim AS web
WORKDIR /build/web
# Primero solo los ficheros de dependencias: mientras no cambien, esta capa se reutiliza.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# El commit que se despliega, para los informes de error de la web (web/src/app/version.ts).
# Va justo antes del build: así cambiarlo no invalida la capa de `npm ci`.
ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA
RUN npm run build

# --- Etapa 2: el servidor. ---
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# El commit que se despliega, para saber qué corre (se ve en /api/health). .git no entra en
# la imagen, así que se pasa al construir:  fly deploy --ha=false --build-arg GIT_SHA=$(git rev-parse --short HEAD)
ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA

WORKDIR /app
COPY config.json ./
COPY scraper ./scraper
COPY --from=web /build/site ./site

# Los datos (la lista del grupo) van a un volumen, no a la imagen: el disco de la
# imagen se borra en cada despliegue. ADMIN_TOKEN llega como secreto del alojamiento
# y nunca se escribe aquí: el repositorio es público.
ENV DATA_DIR=/data
VOLUME /data

EXPOSE 8765
CMD ["python", "-m", "scraper.servidor", "--host", "0.0.0.0", "--puerto", "8765"]
