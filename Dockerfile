FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY motorsports/ motorsports/
COPY app.py .

EXPOSE 9198

ENV PORT=9198
ENV LOG_LEVEL=INFO

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9198"]
