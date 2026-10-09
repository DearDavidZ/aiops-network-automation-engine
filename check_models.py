"""Catálogo de modelos y prueba explícita de inferencia con datos sintéticos."""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.core.ai_analyzer import analyze_telemetry
from src.core.ai_config import AIConfigurationError, AISettings

logger = logging.getLogger("ModelAudit")


def audit_authorized_models() -> int:
    """El catálogo no garantiza acceso a inferencia ni cuota. Limita a 100 modelos."""
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    client: genai.Client | None = None
    try:
        settings = AISettings.from_environment()
        client = genai.Client(
            api_key=settings.api_key,
            vertexai=False,
            enterprise=False,
            http_options=settings.http_options(),
        )
        count = 0
        for index, model in enumerate(
            client.models.list(config=types.ListModelsConfig(page_size=100))
        ):
            if "generateContent" in (model.supported_actions or []):
                print(f"Modelo publicado con generateContent: {model.name}")
                count += 1
            if index >= 99:
                print("Límite local: se revisaron los primeros 100 modelos.")
                break
        print(f"Catálogo consultado: {count} modelos con generación. Acceso no verificado.")
        return 0
    except AIConfigurationError as exc:
        logger.error("Configuración: %s", exc)
        return 1
    except Exception as exc:
        logger.error("Consulta del catálogo fallida: %s", type(exc).__name__)
        return 1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                logger.warning("Fallo al cerrar cliente: %s", type(exc).__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe", action="store_true", help="Consume API con un log sintético fijo"
    )
    args = parser.parse_args()
    if not args.probe:
        return audit_authorized_models()
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    result = analyze_telemetry(
        device_name="synthetic-node",
        payload="Synthetic laboratory event: interface ethernet1 changed state to down.",
    )
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
