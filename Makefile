.PHONY: up down logs migrate seed test shell reset up-dev

up:
	DOCKER_UID=$$(id -u) DOCKER_GID=$$(id -g) docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec fastapi alembic upgrade head

seed:
	docker compose exec fastapi python scripts/seed.py

test:
	docker compose exec fastapi pytest

shell:
	docker compose exec fastapi bash

reset:
	docker compose down -v

up-dev: reset up migrate seed
