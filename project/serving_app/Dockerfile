FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY serving_app/ serving_app/
COPY data/ data/
COPY scripts/ scripts/
ENV PYTHONUTF8=1 TF_ENABLE_ONEDNN_OPTS=0 TF_CPP_MIN_LOG_LEVEL=3
ENV SOLAR_STATE_DIR=/runtime EXECUTION_UNIT=container
EXPOSE 8099
CMD ["python", "scripts/run_backend.py", "--host", "0.0.0.0", "--port", "8099"]
