# CI/CD

Пайплайны в [`.github/workflows/`](../.github/workflows/). Прод-образ собирается для **linux/amd64** и **linux/arm64** и публикуется одним манифестом. Каждая архитектура собирается на своём раннере, без QEMU.

## Workflows

| Workflow | Триггер | Назначение |
| --- | --- | --- |
| **Deploy** (`deploy.yml`) | Push в `main` / `dev`, ручной запуск | Dev-образ и `scripts/ci-test.sh` на amd64 и arm64 |
| **Deploy → prerelease** | Push в `dev` с `[prerelease]` в коммите, или ручной флаг `publish_prerelease` | Образ `:prerelease` в GHCR |
| **Publish** (`publish.yml`) | Успешный Deploy на `main` | Образ `:main` в GHCR |

## Образ GHCR

```
ghcr.io/<owner>/service-template
```

`<owner>` — имя владельца репозитория в нижнем регистре. В compose-оверлеях его задаёт `GHCR_OWNER` (по умолчанию `shiwarai`).

Теги: `:main`, `:prerelease`, `:<git-sha>`.

## Prerelease

Автоматически — коммит в `dev` с меткой в сообщении:

```bash
git commit -m "feat: обновление API [prerelease]"
git push origin dev
```

Вручную — Actions → Deploy → Run workflow → включить `publish_prerelease`.

Сборка идёт матрицей:

| Платформа | Раннер | Кэш BuildKit |
| --- | --- | --- |
| linux/amd64 | `ubuntu-latest` | `service-template-prerelease-linux-amd64` |
| linux/arm64 | `ubuntu-24.04-arm` | `service-template-prerelease-linux-arm64` |

Каждый job пушит образ по digest. Отдельный job склеивает манифест в `:prerelease` и `:<sha>`.

Job **test** кэшируется отдельно: `service-template-dev-linux-amd64` и `service-template-dev-linux-arm64`.

Workflow **Publish** (`:main`) — scope `service-template-main-linux-amd64` и `service-template-main-linux-arm64`.

Оверлеи снимают локальный `build` тегом `!reset null` (в Compose 5 `!override null` не обнуляет секцию).

На стенде:

```bash
docker pull "ghcr.io/${GHCR_OWNER:-shiwarai}/service-template:prerelease"
docker compose -f docker-compose.yml -f docker-compose.prerelease.yml up -d
```

## Stable (main)

После merge в `main` и зелёного Deploy публикуется `:main`:

```bash
docker pull "ghcr.io/${GHCR_OWNER:-shiwarai}/service-template:main"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Локальные тесты (как в CI)

```bash
docker compose -f docker-compose.dev.yml build dev
docker compose -f docker-compose.dev.yml run --rm -T dev ./scripts/ci-test.sh
```

Локально проверяется архитектура хоста. В CI та же команда запускается и на amd64, и на arm64.

## Telegram-уведомления

Secrets репозитория (Settings → Secrets and variables → Actions):

| Secret | Назначение |
| --- | --- |
| `TELEGRAM_TOKEN` | Токен бота |
| `TELEGRAM_TO` | Chat ID |

Без secrets шаги уведомлений не падают (`continue-on-error: true`). Успешные события — тихие (`disable_notification`).

## Требования к репозиторию

- Включены **GitHub Actions** и **Packages** (GHCR).
- Для публичного образа: visibility пакета → Public (при необходимости).
- Раннер `ubuntu-24.04-arm` доступен у GitHub-hosted runners. Self-hosted и QEMU не нужны.

## Что добавить под конкретный сервис

Шаблон не тащит устройства NPU, тома моделей и внешнюю docker-сеть — это не общий каркас.

- Модели и устройства RK3588 (`/dev/dri`, `/dev/dma_heap`, `/dev/mpp_service`, `/dev/rga`) — в `docker-compose.yml` у сервиса, не в dev-compose.
- Несколько образов — отдельные Dockerfile и отдельные шаги сборки в `publish.yml`, как в RDS и video-descriptor.
- Команда тестов — тело `scripts/ci-test.sh`. Target `dev` в `Dockerfile` оставьте без прод-зависимостей NPU.
