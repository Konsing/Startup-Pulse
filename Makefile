.PHONY: up down restart logs init-bq build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f

init-bq:
	docker compose exec airflow-webserver python -m src.utils.init_bq

build:
	docker compose build
