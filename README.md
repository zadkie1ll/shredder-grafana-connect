# shredder-grafana-connect

Микросервис синхронизирует ноды панели с Prometheus `file_sd`: на новых или
изменившихся нодах через SSH проверяет и при необходимости устанавливает
`node_exporter`, а затем атомарно обновляет JSON targets. Grafana получает новые
ряды через существующий Prometheus автоматически.

## Возможности

- запрос Panel API с тремя попытками и безопасным отказом без изменения targets;
- строгий машиночитаемый блок `monitoring:` в notes;
- SSH TOFU (`accept-new`) с отдельным `known_hosts` и блокировкой изменившихся ключей;
- idempotent установка `node_exporter` с проверкой SHA-256 и `/metrics`;
- SQLite-состояние, обнаружение новых, изменённых и удалённых нод;
- защищённые от удаления ноды по UUID или имени;
- атомарная запись Prometheus `file_sd`;
- hourly APScheduler, lock от параллельных sync и ручной защищённый запуск;
- `/health`, `/ready`, `/metrics`, `/api/v1/sync/status`, `/api/v1/nodes`;
- JSON-логи без токенов, ключей и полного содержимого notes.

## Формат notes

```text
monitoring:
ssh_host=1.2.3.4
ssh_port=22
ssh_user=root
node_exporter_port=9100
enabled=true
```

Обязателен `ssh_user`. Если `ssh_host` отсутствует, используется address/IP из
Panel API. Допустимы только перечисленные поля. `enabled=false` исключает ноду.

## Конфигурация

```bash
cp .env.example .env
```

Заполните как минимум `PANEL_BASE_URL`, `PANEL_API_TOKEN` и
`ADMIN_API_TOKEN`. `PANEL_NODES_PATH` задаёт endpoint списка нод. Поддерживаются
ответы-массивы и обёртки `nodes`, `data`, `response`, включая
`response.nodes`.

По умолчанию пустой список API отклоняется (`PANEL_ALLOW_EMPTY_RESPONSE=false`),
чтобы из-за ошибочного endpoint/формата не удалить все targets. Включайте опцию
только если панель действительно может штатно не содержать ни одной ноды.

Ноды, которые нельзя удалять из generated targets при исчезновении из панели,
задаются списками через запятую:

```env
PROTECTED_NODE_IDS=panel-uuid,bot-uuid
PROTECTED_NODE_NAMES=panel,bot
```

Имена сравниваются без учёта регистра. По умолчанию защищены точные имена
`panel` и `bot`; для production надёжнее дополнительно указать их UUID.
Сервис владеет только `nodes.json` и никогда не изменяет другие target-файлы,
например `infra.json` со статическими системными серверами.

На Docker host укажите:

```env
SSH_KEY_HOST_PATH=/root/.ssh/id_ed25519
PROMETHEUS_TARGETS_HOST_DIR=/root/apps/vpn-monitoring/prometheus/targets
```

Приватный ключ монтируется read-only и никогда не копируется на удалённые ноды.

## Запуск

```bash
docker compose config
docker compose up -d --build
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/ready
```

Ручная синхронизация:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  http://127.0.0.1:8080/api/v1/sync
```

Prometheus должен монтировать ту же директорию в `/etc/prometheus/targets` и
иметь один раз настроенный `file_sd_configs`. Пример находится в
`prometheus/prometheus-scrape.example.yml`.

## Проверки

```bash
python -m pip install -e '.[test]'
ruff check .
pytest
```

Unit tests не выполняют реальные SSH-подключения.

## Развёртывание на ru4

Рекомендуемый каталог: `/root/apps/shredder-grafana-connect`. До запуска
проверьте, что `/root/.ssh/id_ed25519` существует и этим ключом можно войти на
все управляемые ноды. Затем создайте `.env`, подключите существующий каталог
targets и запустите Compose.
