# rag-parser

Microservicio FastAPI para parsing de documentos (PDF, DOCX) e ingesta en Supabase pgvector. Pensado para usarse junto a una app Next.js deployada en Vercel.

**Stack:** Docling · OpenAI Embeddings · Supabase pgvector · FastAPI

---

## Deploy en EasyPanel

### 1. Crear el servicio

1. En EasyPanel → **Create Service → App**
2. Conectar tu repo de GitHub (o subir el código directo)
3. EasyPanel detecta el `Dockerfile` automáticamente

### 2. Variables de entorno

En la pestaña **Environment** del servicio, agregar:

```
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
INTERNAL_TOKEN=<generá uno con: openssl rand -hex 32>
```

Las variables opcionales tienen defaults razonables, pero podés sobreescribirlas:

```
SUPABASE_TABLE=documents
EMBED_MODEL=text-embedding-3-small
CHUNK_MAX_TOKENS=512
EMBED_BATCH_SIZE=32
```

### 3. Dominio

En la pestaña **Domains**, EasyPanel te genera un dominio automáticamente. Copialo y pegalo en tu `.env.local` de Vercel:

```
PARSER_SERVICE_URL=https://rag-parser.tudominio.com
INTERNAL_TOKEN=<el mismo token que pusiste en EasyPanel>
```

### 4. Recursos recomendados

Docling descarga modelos de AI (~500MB). Recomendado:

- **RAM:** 1GB mínimo, 2GB recomendado
- **CPU:** 1 vCPU es suficiente para uso moderado
- **Disco:** 2GB mínimo (para los modelos de Docling)

---

## Endpoints

### `GET /health`
Verifica que el servicio esté corriendo.

```bash
curl https://rag-parser.tudominio.com/health
```

### `POST /parse`
Parsea un archivo e inserta los chunks en Supabase.

```bash
curl -X POST https://rag-parser.tudominio.com/parse \
  -H "x-internal-token: TU_TOKEN" \
  -F "file=@documento.pdf" \
  -F "user_id=user_123"
```

**Response:**
```json
{ "status": "ok", "chunks_inserted": 42 }
```

---

## Uso desde Next.js

### `app/api/upload/route.ts`

```typescript
export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("file") as File;
  const userId = formData.get("user_id") as string;

  const parserForm = new FormData();
  parserForm.append("file", file);
  parserForm.append("user_id", userId ?? "");

  const res = await fetch(`${process.env.PARSER_SERVICE_URL}/parse`, {
    method: "POST",
    headers: { "x-internal-token": process.env.INTERNAL_TOKEN! },
    body: parserForm,
  });

  if (!res.ok) {
    return NextResponse.json({ error: "Parsing failed" }, { status: 500 });
  }

  return NextResponse.json(await res.json());
}
```

---

## Desarrollo local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Crear .env desde el ejemplo
cp .env.example .env
# Editar .env con tus valores

# Correr el servidor
uvicorn main:app --reload --port 8000
```

La primera vez que se inicia, Docling descarga los modelos (~500MB). Esto ya está pre-cacheado en la imagen Docker para evitar el delay en producción.
