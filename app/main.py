import asyncio
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import Settings, get_settings
from app.logging import configure_logging, log
from app.models import ManagedNode, SyncResult
from app.panel.client import PanelClient
from app.repository import NodeRepository
from app.services import NodeSyncService
from app.ssh.client import SSHClient
from app.ssh.installer import NodeExporterInstaller


def build_service(settings: Settings) -> tuple[NodeRepository, NodeSyncService]:
    repository = NodeRepository(settings.database_path)
    ssh = SSHClient(settings)
    service = NodeSyncService(
        PanelClient(settings),
        repository,
        NodeExporterInstaller(settings, ssh),
        settings.prometheus_targets_file,
    )
    return repository, service


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    repository, service = build_service(settings)
    await repository.initialize()
    settings.prometheus_targets_file.parent.mkdir(parents=True, exist_ok=True)
    app.state.settings = settings
    app.state.repository = repository
    app.state.sync_service = service
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        service.sync,
        "interval",
        seconds=settings.sync_interval_seconds,
        max_instances=1,
        coalesce=True,
        id="node-sync",
    )
    scheduler.start()
    app.state.scheduler = scheduler
    if settings.run_sync_on_startup:
        asyncio.create_task(service.sync())
    log.info("service_started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        log.info("service_stopped")


app = FastAPI(title="Shredder Grafana Connect", version="0.1.0", lifespan=lifespan)


def get_repository(request: Request) -> NodeRepository:
    return request.app.state.repository


def get_sync_service(request: Request) -> NodeSyncService:
    return request.app.state.sync_service


def require_admin(request: Request, authorization: str | None = Header(None)) -> None:
    expected = f"Bearer {request.app.state.settings.admin_api_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(
    request: Request,
    repository: Annotated[NodeRepository, Depends(get_repository)],
) -> dict[str, str]:
    targets_dir = Path(request.app.state.settings.prometheus_targets_file).parent
    if not await repository.ready() or not targets_dir.is_dir():
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready"}


@app.get("/api/v1/sync/status", response_model=SyncResult | None)
async def sync_status(
    service: Annotated[NodeSyncService, Depends(get_sync_service)],
) -> SyncResult | None:
    return service.last_result


@app.post("/api/v1/sync", response_model=SyncResult, dependencies=[Depends(require_admin)])
async def trigger_sync(
    service: Annotated[NodeSyncService, Depends(get_sync_service)],
) -> SyncResult:
    return await service.sync()


@app.get("/api/v1/nodes", response_model=list[ManagedNode], dependencies=[Depends(require_admin)])
async def list_nodes(
    repository: Annotated[NodeRepository, Depends(get_repository)],
) -> list[ManagedNode]:
    return await repository.get_nodes(include_removed=True)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
