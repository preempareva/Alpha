FROM python:3.12-slim
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY docs ./docs
ENV DATABASE_PATH=/var/lib/knowledge/knowledge.db
EXPOSE 8000
CMD ["sh", "-c", "python scripts/seed_demo.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
