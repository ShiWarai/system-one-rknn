# system-one-rknn

Сервис инференса для NPU Rockchip RK3588: Laya multilingual (RKNN 2.3.2) и Kev-0.8B (RKLLM 1.3.1) по HTTP API. CI, Docker и документация.

Чтобы GitHub показывал кнопку **Use this template**, в репозитории-источнике включите **Settings → General → Template repository**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20linux%2Farm64-orange.svg)
![Docker](https://img.shields.io/badge/docker-GHCR-blue.svg)

## Стек технологий

| Категория | Технологии |
| --- | --- |
| Приложение | Python 3 (stdlib `http.server` + numpy + tokenizers), порт 8080 |
| Тесты | `ruff check` + `python -m unittest`, команда в `scripts/ci-test.sh` |
| Инфраструктура | Docker, Docker Compose, GitHub Actions, GHCR |

## Оглавление

- [Быстрый старт](#быстрый-старт)
- [Новый репозиторий из шаблона](#новый-репозиторий-из-шаблона)
- [Установка и запуск](#установка-и-запуск)
- [Тесты](#тесты)
- [CI/CD](#cicd)
- [Инструкции для агента](#инструкции-для-агента)
- [Лицензия](#лицензия)
- [Авторские права](#авторские-права)

## Быстрый старт

```bash
cp .env.example .env
docker compose build
docker compose up -d --wait
curl -fsS "http://127.0.0.1:${PORT:-8080}/health"
```

API:

- `GET /health` — статус и список загруженных моделей.
- `GET /v1/models` — каталог моделей.
- `POST /v1/systemone` — вопросы трёх типов (`choice`, `noul`, `score`); в ответе вероятности, уверенность и `latency_ms`.

Переменные — в `.env.example`: `PORT`, `GHCR_OWNER`, `SYSTEM_ONE_ENGINE` (`npu` или `fake`), `MODELS` (`laya`, `kev`), `MODELS_DIR`, `LAYA_REPO`, `KEV_REPO`, `BOARD`.

Образ из GHCR, без локальной сборки:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Новый репозиторий из шаблона

1. **Use this template** → Create a new repository.
2. Включите Actions и Packages (GHCR).
3. Замените имя сервиса (slug из строчных латинских букв, цифр и дефисов):

```bash
./scripts/bootstrap.sh my-service
```

4. Замените `CMD` в `Dockerfile` (target `runtime`) и тело `scripts/ci-test.sh` на свой процесс и свои тесты. `scripts/stub-server.sh` отвечает `ok` на `GET /health` и нужен только чтобы шаблон поднимался.

Секреты репозитория для уведомлений: `TELEGRAM_TOKEN`, `TELEGRAM_TO`. Без них шаги Telegram не роняют workflow.

## Установка и запуск

Локальная сборка — `docker-compose.yml`, target `runtime`.

Кандидат на проверку (`:rk3588-prerelease`):

```bash
docker pull "ghcr.io/${GHCR_OWNER:-shiwarai}/system-one-rknn:rk3588-prerelease"
docker compose -f docker-compose.yml -f docker-compose.prerelease.yml up -d
```

Продакшен (`:rk3588-main`):

```bash
docker pull "ghcr.io/${GHCR_OWNER:-shiwarai}/system-one-rknn:rk3588-main"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`GHCR_OWNER` задаётся в `.env` (по умолчанию `shiwarai`).

## Тесты

Как в CI, на архитектуре хоста:

```bash
docker compose -f docker-compose.dev.yml build dev
docker compose -f docker-compose.dev.yml run --rm -T dev ./scripts/ci-test.sh
```

`scripts/ci-test.sh` запускает `ruff check app tests` и `python -m unittest discover -s tests`.

## CI/CD

Пайплайны: [docs/cicd.md](docs/cicd.md).

| Тег | Когда |
| --- | --- |
| `:rk3588-main` | Успешный Deploy на `main` |
| `:rk3588-prerelease` | Push в `dev` с `[prerelease]` в сообщении коммита или ручной флаг |
| `:rk3588-<sha>` | Тот же билд, что `:rk3588-main` или `:rk3588-prerelease` |

Образы `linux/amd64` и `linux/arm64` собираются на нативных раннерах GitHub и публикуются одним манифестом.

## Инструкции для агента

Постоянный контракт для агентов — [AGENTS.md](AGENTS.md): реальные тесты, включая интеграционные, компактный образ, линтер после правок, README только перед коммитом.

## Лицензия

Проект распространяется по лицензии [MIT](https://opensource.org/licenses/MIT).
