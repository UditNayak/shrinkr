FROM python:3.14-slim
WORKDIR /code

# dependencies first, so code changes don't reinstall them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# same image runs the worker and migrations, compose overrides the command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
