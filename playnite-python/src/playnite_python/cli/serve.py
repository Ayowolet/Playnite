"""CLI command to start the Playnite Python service."""
import typer
import uvicorn
from loguru import logger

from ..core.config import settings

app = typer.Typer(help="Start the Playnite Python service")


@app.command()
def start(
    host: str = typer.Option(
        settings.host,
        "--host",
        "-h",
        help="Host to bind the service to",
    ),
    port: int = typer.Option(
        settings.port,
        "--port",
        "-p",
        help="Port to bind the service to",
    ),
    reload: bool = typer.Option(
        settings.reload,
        "--reload",
        "-r",
        help="Enable auto-reload for development",
    ),
):
    """
    Start the Playnite Python service.

    This starts the FastAPI server that handles game recommendations
    and media capture functionality.
    """
    logger.info(f"Starting service on {host}:{port}")
    if reload:
        logger.warning("Reload mode enabled - for development only!")

    try:
        uvicorn.run(
            "playnite_python.api.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Service failed to start: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
