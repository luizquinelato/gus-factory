<!-- blueprint: db_changes=false seed_data=false -->
# 11. ETL Layer (Extraction, Transform, Load)

This document details the ETL layer architecture, active when `{{ ENABLE_ETL }} = true`.

## 🔄 1. Queue and Worker Architecture

The system uses `{{ QUEUE_LAYER }}` (e.g.: RabbitMQ) to orchestrate the data flow in 3 isolated stages:

1. **Extraction Queue**: Receives jobs to fetch raw data from external APIs (e.g.: invoices, bank statements).
2. **Transform Queue**: Processes raw data, cleans, normalizes and saves to business tables.
3. **Embedding Queue** (if `{{ ENABLE_AI_LAYER }} = true`): Generates vectors from transformed data and saves to `{{ EMBEDDING_DB }}`.

## ⚙️ 2. Worker and Buffer Configuration

The number of workers and the batch size **must not be hardcoded**. They should be read from the `system_settings` table to allow fine-tuning in production without a deploy.

```json
// Example configuration in the system_settings table
[
  {
    "setting_key": "extraction_workers_count",
    "setting_value": "5"
  },
  {
    "setting_key": "etl_batch_size",
    "setting_value": "100"
  }
]
```

The `WorkerManager` is responsible for reading these settings and instantiating the correct number of processes. The RabbitMQ `prefetch_count` should be configured based on the `batch_size` to optimize memory consumption.

## 📊 3. Worker Status Manager

To avoid complex inheritance, use the Composition pattern with a `WorkerStatusManager`. It is injected into workers and is responsible for:

1. Updating the job status in the database (`etl_jobs` table).
2. Firing events via WebSocket so the frontend updates the UI in real time.

```python
# services/backend/app/etl/workers/status_manager.py
class WorkerStatusManager:
    def __init__(self, db_session, websocket_manager):
        self.db = db_session
        self.ws = websocket_manager

    def update_status(self, job_id: int, status: str, progress: int = 0):
        # Update in database
        job = self.db.query(EtlJob).filter(EtlJob.id == job_id).first()
        if job:
            job.status = status
            job.progress = progress
            self.db.commit()

        # Notify the frontend
        self.ws.broadcast_to_tenant(
            tenant_id=job.tenant_id,
            message={"type": "ETL_STATUS", "job_id": job_id, "status": status, "progress": progress}
        )
```
