.PHONY: up down install migrate test lint api

up:
	docker compose up -d postgres

down:
	docker compose down

install:
	cd backend && pip install -e ".[dev]"

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check app tests

api:
	cd backend && fastapi dev app/main.py
