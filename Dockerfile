# Usa un'immagine ufficiale di Python 3.13
FROM python:3.13-slim

# Imposta la directory di lavoro
WORKDIR /app

# Installa pipenv e le dipendenze di sistema (necessarie per psycopg2 e SpeechRecognition)
RUN pip install --no-cache-dir pipenv && \
    apt-get update && apt-get install -y --no-install-recommends gcc python3-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia i file di dipendenza
COPY Pipfile Pipfile.lock ./

# Installa le dipendenze direttamente nel sistema del container
RUN pipenv install --system --deploy

# Copia il resto del codice
COPY . .

# Esponi la porta 8080 (quella predefinita di Cloud Run)
EXPOSE 8080

# Avvia FastAPI con Uvicorn
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]