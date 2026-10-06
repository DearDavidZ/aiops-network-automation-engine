# ⚡ AIOps Network Automation Engine

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Nornir](https://img.shields.io/badge/Nornir-3.4.1-success.svg)
![Netmiko](https://img.shields.io/badge/Netmiko-Supported-orange.svg)
![AI](https://img.shields.io/badge/GenAI-Google_Gemini-purple.svg)
![Status](https://img.shields.io/badge/Status-Production_Ready-brightgreen.svg)

## Visión General
Motor de observabilidad proactiva y automatización de redes diseñado bajo principios de **Site Reliability Engineering (SRE)**. Esta plataforma emplea ejecución concurrente (Nornir) para extraer telemetría de nodos de red y canaliza las excepciones de conectividad hacia un Modelo de Lenguaje (LLM) para emitir diagnósticos técnicos heurísticos, reduciendo el Tiempo Medio de Resolución (MTTR).

## Arquitectura y Patrones SRE Implementados
* **Orquestación Concurrente:** Procesamiento multihilo nativo para escalar masivamente.
* **Seguridad Zero-Trust:** Inyección dinámica de credenciales en memoria (In-Memory Credential Injection).
* **Tolerancia a Fallos (Circuit Breaker):** Intercepción algorítmica de caídas de proveedores Cloud con degradación elegante hacia diagnósticos de contingencia local.

## Guía de Despliegue (Reproducibilidad)
1. Clonar repositorio e inicializar entorno virtual (`python -m venv .venv`).
2. Instalar manifiesto inmutable: `pip install -r requirements.txt`
3. Aprovisionar bóveda Zero-Trust creando un archivo `.env` basado en la plantilla `.env.example`.
4. Ejecutar orquestador: `python -m src.run_engine`