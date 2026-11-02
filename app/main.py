import os
import random
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode


SERVICE_NAME = os.getenv(
    "OTEL_SERVICE_NAME",
    "corporate-transactions-api",
)

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "http://otel-collector.observability.svc.cluster.local:4318/v1/traces",
)

resource = Resource.create({
    "service.name": SERVICE_NAME,
    "service.version": "1.1.0",
    "deployment.environment.name": "lab",
})

tracer_provider = TracerProvider(resource=resource)

tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=OTEL_ENDPOINT, timeout=5)
    )
)

trace.set_tracer_provider(tracer_provider)

tracer = trace.get_tracer(__name__)

app = FastAPI(
    title="Corporate Transactions API",
    description="Enterprise transaction simulation for SRE studies",
    version="1.1.0",
)

FastAPIInstrumentor.instrument_app(
    app,
    tracer_provider=tracer_provider,
    excluded_urls="/health,/ready,/metrics",
)

TRANSACTIONS = Counter(
    "corporate_transactions_total",
    "Total number of simulated transactions",
    ["status"],
)

LATENCY = Histogram(
    "corporate_transaction_duration_seconds",
    "Duration of simulated operations in seconds",
)


class TransactionRequest(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "BRL"


@app.get("/")
def home():
    return {
        "application": "Corporate Transactions API",
        "project": "CloudOps Reliability Lab",
        "version": "1.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def readiness():
    return {"status": "ready"}


@app.post("/transactions")
def create_transaction(request: TransactionRequest):
    start = time.perf_counter()

    with tracer.start_as_current_span("process_transaction") as span:
        span.set_attribute("transaction.currency", request.currency)

        try:
            time.sleep(random.uniform(0.05, 0.3))

            transaction = {
                "transaction_id": str(uuid.uuid4()),
                "amount": request.amount,
                "currency": request.currency,
                "status": "approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            span.set_attribute("transaction.status", "approved")
            TRANSACTIONS.labels(status="approved").inc()

            return transaction

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise

        finally:
            LATENCY.observe(time.perf_counter() - start)


@app.get("/simulate/error")
def simulate_error():
    with tracer.start_as_current_span("simulate_transaction_error") as span:
        TRANSACTIONS.labels(status="error").inc()

        span.set_attribute("transaction.status", "error")
        span.set_status(
            Status(StatusCode.ERROR, "Simulated internal processing failure")
        )

        raise HTTPException(
            status_code=500,
            detail="Simulated internal processing failure",
        )


@app.get("/simulate/latency")
def simulate_latency():
    start = time.perf_counter()

    with tracer.start_as_current_span("simulate_high_latency") as span:
        try:
            time.sleep(3)
            span.set_attribute("simulation.delay_seconds", 3)

            return {
                "status": "completed",
                "delay_seconds": 3,
            }

        finally:
            LATENCY.observe(time.perf_counter() - start)


@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
