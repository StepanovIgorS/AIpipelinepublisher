# AI Pipeline Publisher

**A microservice-based backend for asynchronous content processing.**

AI Pipeline Publisher is a Telegram bot that turns supported video and article links into post-ready text adapted to a user's chosen platform, audience, length, and writing instructions.

The backend separates request handling from long-running processing: the FastAPI service accepts Telegram webhook updates and manages user/task state, while Celery workers handle article parsing, video downloading, transcription, and AI summarization. Redis decouples API requests from background jobs, and PostgreSQL stores durable application state. The API, worker, and scheduler run as separate Docker Compose services with focused responsibilities.

## Features

- Accepts video links from YouTube, Rutube, and VK Video.
- Extracts article content from Habr, Pikabu, and Dzen.
- Downloads video and prepares audio for speech-to-text transcription.
- Generates an adapted summary using a configurable OpenAI-compatible API.
- Lets users configure their target platform, audience, preferred text length, and custom prompt.
- Tracks task statuses and stores user settings and payment records in PostgreSQL.
- Uses Celery and Redis to process tasks asynchronously.
- Supports Premium subscriptions through Telegram Payments.
- Caches transcriptions and periodically cleans up expired cache entries.

## Microservice architecture

The application is split into independently running application services rather than performing the entire workflow inside the HTTP request handler:

- **API service** — handles the Telegram webhook, user interactions, task creation, payment callbacks, and task status/completion endpoints.
- **Worker service** — performs slow or resource-intensive work outside the API process: downloading media, parsing articles, preparing audio, transcription, and text generation.
- **Beat service** — schedules periodic background jobs such as cache cleanup.

The API dispatches jobs through Celery using Redis as the broker/backend. The worker reports task status and completion back to the API through internal HTTP endpoints. PostgreSQL stores users, task state, and payment records. Docker Compose runs these components as separate containers and starts the application services after the database migration step succeeds.

This is a compact microservice-oriented design focused on separating synchronous request handling from asynchronous processing; it is not intended to claim the operational complexity of a large production distributed system.

```mermaid
flowchart LR
    User[Telegram user] -->|Webhook update| API[FastAPI API]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis broker/backend)]
    Redis --> Worker[Celery worker]
    Worker --> Sources[Article parsers / video processing]
    Sources --> AI[Speech-to-text / text generation API]
    AI --> Worker
    Worker -->|Status and completion callbacks| API
    Worker -->|Generated text| User
    Beat[Celery Beat] -->|Periodic cache cleanup| Redis
    Migrate[Migration service] -->|Alembic upgrade head| DB
```

### Services

| Service | Responsibility |
| --- | --- |
| `api-service` | FastAPI application, Telegram webhook, user interactions, task and payment records |
| `worker-service` | Celery tasks for article parsing, video processing, transcription, and summarization |
| `beat-service` | Schedules periodic cache cleanup tasks |
| `migrate` | Applies pending database migrations before API and Worker start |
| `postgres` | Stores users, processing tasks, and payments |
| `redis` | Celery broker and result backend |

### Architectural decisions

- **Asynchronous job processing:** long-running media and AI work is handled by Celery workers instead of blocking the webhook/API request path.
- **Queue-based decoupling:** Redis carries jobs between the API and worker processes.
- **Separate runtime responsibilities:** API, worker, and scheduler are built/run as separate Docker Compose services.
- **Explicit database evolution:** Alembic applies versioned SQL migrations, while the application continues to use `asyncpg` without ORM models.

## Tech stack

- **Python 3.11**
- **FastAPI** and **aiogram**
- **Celery** and **Redis**
- **PostgreSQL** and **asyncpg**
- **Alembic** for schema migrations using plain SQL; no ORM models are required
- **yt-dlp** for video downloading
- **Beautiful Soup** and **Requests** for article extraction
- **pytest** for automated tests
- **Docker Compose** for local deployment

## Requirements

- Docker Engine and Docker Compose v2
- A Telegram bot token
- An OpenAI-compatible API endpoint and API key for transcription and text generation
- A publicly reachable HTTPS URL for the Telegram webhook (a tunnel can be used during local development)
- A Telegram Payments provider token if testing subscription payments

## Configuration

Create a `.env` file in the repository root. Do not commit this file or put real credentials in the repository. Start from the example below and replace the placeholders:

```dotenv
# PostgreSQL. Keep these values consistent with POSTGRES_URL.
POSTGRES_USER=user
POSTGRES_PASSWORD=replace_with_local_password
POSTGRES_DB=pipeline
POSTGRES_URL=postgresql://user:replace_with_local_password@postgres:5432/pipeline

# Redis, addressed by the Compose service name from inside containers.
REDIS_URL=redis://redis:6379/0

# Telegram
BOT_TOKEN=replace_with_telegram_bot_token
WEBHOOK_URL=https://your-public-host.example/webhook
TELEGRAM_SECRET_TOKEN=replace_with_webhook_secret
INTERNAL_SECRET=replace_with_internal_service_secret
PAYMENT_TOKEN=replace_with_telegram_payment_provider_token

# OpenAI-compatible provider used by the worker
AI_URL=https://your-openai-compatible-provider.example/v1
AI_KEY=replace_with_ai_api_key
AI_STT_MODEL=your_speech_to_text_model
AI_TEXT_MODEL=your_text_generation_model
```

Use the same PostgreSQL username, password, and database name in `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `POSTGRES_URL`. Use a URL-safe password, or URL-encode special characters in `POSTGRES_URL`. Keep `.env` out of Git.

The API configures the Telegram webhook during application startup. `WEBHOOK_URL` must point to a publicly reachable HTTPS endpoint that forwards requests to this application's `/webhook` route. The bot token and external API credentials must be valid for those integrations to work.

## Run the project

From the repository root, after creating `.env` and filling in the required credentials, run:

```bash
docker compose up --build
```

Compose builds the images, starts PostgreSQL and Redis, waits for PostgreSQL to become ready, runs `alembic upgrade head` in the one-off `migrate` service, and starts the API and Celery services after migrations succeed. No separate migration command is required for a fresh database.

The API is exposed at `http://localhost:3000`. The Telegram webhook itself must use the public HTTPS address configured in `WEBHOOK_URL`, not `localhost`.

To run in the background instead, use `docker compose up --build -d`. To inspect the running services and logs:

```bash
docker compose ps
docker compose logs -f api-service worker-service beat-service migrate
```

Stop the services while preserving the database volume:

```bash
docker compose down
```

**To reset the local database completely**, run the following from the project root:

```bash
docker compose down -v --remove-orphans
docker compose up --build
```

The `-v` option permanently deletes the Compose-managed PostgreSQL volume, including all data stored in it. Only use it when you really intend to start with an empty database. The migration service will recreate the schema on the next startup. Files in the host-mounted `./cache` directory and `.env` are not deleted by this command.

### Existing database created before Alembic

If PostgreSQL already contains the application's tables but does not have an `alembic_version` record, do not start the `migrate` service against it for the first time: the initial migration would try to create tables that already exist. First verify that the existing schema matches the initial migration, start PostgreSQL, and register the initial revision without executing it:

```bash
docker compose up -d postgres redis
docker compose run --rm --no-deps api-service alembic stamp head
docker compose up --build
```

Only use `stamp head` after confirming the schema really matches the migration. Once the initial revision is registered, subsequent starts can use `docker compose up --build` normally.

## Database migrations

Migration scripts live in `api-service/migrations/versions/`. They use regular SQL executed through Alembic operations, so the application can continue using `asyncpg` without ORM models.

Create a new migration file from the repository root. The temporary mount is used only to write the generated file into the local repository; source code is not mounted into the running application containers:

```powershell
docker compose run --rm --no-deps `
  -v "${PWD}/api-service:/app" `
  api-service alembic revision -m "describe schema change"
```

Edit the generated `upgrade()` and `downgrade()` functions, test the migration against a disposable database, then commit the migration file. On normal startup, the `migrate` service applies pending revisions automatically.

## Tests

The test suite is based on `pytest` and covers selected behavior of URL/platform helpers, context construction, cache handling, audio preparation, video-download task logic, AI task behavior, article parsers, internal API endpoints, and payment handlers. External services are mocked in unit tests, so the unit test suite does not require real AI requests or real Telegram payments.

Install the service dependencies and pytest in a development environment, then run:

```bash
python -m pip install -r api-service/requirements.txt -r worker-service/requirements.txt
python -m pip install pytest
pytest
```

## Future improvements

- Add end-to-end tests for the task-processing pipeline using an isolated test environment.
- Add integration tests for database-dependent behavior and payment state transitions.
- Add Prometheus metrics and Grafana dashboards for observability.
- Improve service readiness checks and deployment automation.
