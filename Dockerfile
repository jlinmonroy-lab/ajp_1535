# Imagen del servidor para un alojamiento fijo (Fly.io). Python puro, sin dependencias:
# no hay nada que instalar. Ver "Alojamiento fijo" en el README.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY config.json ./
COPY scraper ./scraper
COPY site ./site

# Los datos (la lista del grupo) van a un volumen, no a la imagen: el disco de la
# imagen se borra en cada despliegue. ADMIN_TOKEN llega como secreto del alojamiento
# y nunca se escribe aquí: el repositorio es público.
ENV DATA_DIR=/data
VOLUME /data

EXPOSE 8765
CMD ["python", "-m", "scraper.servidor", "--host", "0.0.0.0", "--puerto", "8765"]
