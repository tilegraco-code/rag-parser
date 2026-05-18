FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para Docling (OCR, procesamiento de docs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Predescargar los modelos de Docling en build time
# (evita cold start lento en el primer request)
RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
