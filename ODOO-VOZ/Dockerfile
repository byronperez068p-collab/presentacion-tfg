# Usamos Python oficial
FROM python:3.10-slim

# Instalamos FFmpeg para procesamiento de audio (necesario para Gemini STT/TTS si aplica)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Carpeta de trabajo
WORKDIR /app

# Copiar dependencias e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
# Copiamos la carpeta src completa al contenedor
COPY src/ ./src/

# El bot escucha en el puerto 8080 (Cloud Run lo requiere por defecto)
ENV PORT=8080

# Comando para iniciar usando el módulo src.main
CMD ["python", "-m", "src.main"]
