# Celery + Redis Implementation Guide

## Overview

This document describes the Celery + Redis task queue implementation for the Insurance Policy Comparator. The system enables asynchronous, sequential processing of policy documents through all 7 analysis segments with real-time progress tracking.

## Architecture

### System Components

```
Frontend (React)
    ↓
FastAPI API Server
    ↓ (Submit Job)
Redis (Broker)
    ↓
Celery Worker(s)
    ↓ (Sequential Chain)
Segments 1-7 Pipeline
    ↓
SQLite Stores (Persistence)
    ↓
DeliveryService (Result Assembly)
    ↓
Frontend (Progress Updates via WebSocket)
```

## How It Works

### Job Submission Flow

1. **Frontend** calls `POST /jobs/compare` with two PDF files
2. **API** creates a job record and submits a Celery chain
3. **Redis** queues the task chain
4. **Celery Worker** begins processing segments sequentially
5. **Each segment** updates job progress via Redis pubsub
6. **Frontend** subscribes to WebSocket for real-time updates
7. **Result** stored in job record when complete

### Sequential Processing (Key Feature)

The Celery chain ensures strict sequential execution:

```
Segment 1: Document A Layout → 
Segment 2: Document A Definitions → 
Segment 3: Document A Classification → 
Segment 4: Document A DNA →
Segment 5: Document B Layout → 
Segment 6: Document B Definitions → 
Segment 7: Document B Classification → 
Segment 8: Document B DNA →
Segment 9: Semantic Alignment → 
Segment 10: Delta Interpretation → 
Segment 11: Narrative Summarisation
```

If any segment fails, the entire chain stops and the job status is set to FAILED.

## File Structure

### Backend Files

```
python-backend/
├── celery_app.py                  # Celery configuration
├── websocket_server.py            # WebSocket handlers
├── tasks/
│   ├── __init__.py               # Package init
│   ├── segments.py               # Individual segment tasks (1-7)
│   ├── comparison_chain.py        # Chain orchestration
│   └── callbacks.py              # Progress callbacks
├── routes/
│   └── jobs.py                   # Job API endpoints
├── ucc/
│   ├── storage/
│   │   └── job_store.py          # Job persistence
│   └── delivery/
│       └── service.py            # DeliveryService (result assembly)
└── main.py                        # Updated with job routes
```

### Frontend Files

```
src/
├── utils/
│   └── pythonApiClient.ts        # Job submission + WebSocket methods
├── components/
│   ├── PolicyWordingComparator.tsx  # Updated for async mode
│   └── clause/
│       └── JobProgressPanel.tsx     # Progress UI component
```

### Infrastructure

```
docker-compose.yml                # Multi-service orchestration
Dockerfile.frontend               # React dev container
python-backend/Dockerfile         # Updated for Celery
```

## API Endpoints

### Job Submission

**POST `/jobs/compare`**
- Submit a new comparison job
- Returns `job_id` and `celery_task_id`
- Accepts two PDF files

```bash
curl -X POST http://localhost:8000/jobs/compare \
  -F "file_a=@policy_a.pdf" \
  -F "file_b=@policy_b.pdf"
```

Response:
```json
{
  "job_id": "uuid-string",
  "celery_task_id": "task-uuid",
  "status": "QUEUED",
  "message": "Job submitted successfully"
}
```

### Get Job Status

**GET `/jobs/{job_id}`**
- Get current progress of a job
- Returns detailed status with segment information

```bash
curl http://localhost:8000/jobs/abc123
```

Response:
```json
{
  "job_id": "abc123",
  "status": "RUNNING",
  "current_segment": 5,
  "current_segment_name": "Document B: Layout Analysis",
  "progress_pct": 45.5,
  "total_segments": 11
}
```

### Get Job Result

**GET `/jobs/{job_id}/result`**
- Retrieve full comparison results when complete
- Returns 202 if still processing

```bash
curl http://localhost:8000/jobs/abc123/result
```

### Cancel Job

**POST `/jobs/{job_id}/cancel`**
- Cancel a running job

```bash
curl -X POST http://localhost:8000/jobs/abc123/cancel
```

### List Jobs

**GET `/jobs`**
- List all jobs with optional filtering

```bash
curl "http://localhost:8000/jobs?status=RUNNING&limit=50"
```

## WebSocket Real-Time Updates

**Connect to**: `ws://localhost:8000/ws/jobs/{job_id}`

Receive real-time progress updates:

```json
{
  "type": "progress",
  "job_id": "abc123",
  "segment": 5,
  "segment_name": "Document B: Layout Analysis",
  "progress_pct": 45.5,
  "status": "RUNNING",
  "timestamp": "2024-01-15T10:30:45.123Z"
}
```

## Running the System

### With Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api
docker-compose logs -f celery-worker

# Scale workers
docker-compose up -d --scale celery-worker=4

# Stop all
docker-compose down

# Access Flower monitoring
# http://localhost:5555
```

### Manual Setup

```bash
# Install dependencies
cd python-backend
pip install -r requirements.txt

# Start Redis
redis-server

# Start Celery worker (in separate terminal)
celery -A celery_app worker --loglevel=info

# Start API server (in separate terminal)
uvicorn main:app --host 0.0.0.0 --port 8000

# Start frontend (in separate terminal)
npm run dev
```

## Configuration

### Environment Variables

```bash
# Celery/Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Database paths
UCC_LAYOUT_DB_PATH=/data/layout.db
UCC_JOBS_DB_PATH=/data/jobs.db

# API Server
PORT=8000
```

### Celery Settings (celery_app.py)

- **Broker**: Redis at `/0`
- **Result Backend**: Redis at `/1`
- **Task Timeout**: 600s hard limit, 540s soft limit
- **Worker Concurrency**: 2 (configurable)
- **Task Tracking**: Enabled
- **Retry**: Automatic on transient failures

## Monitoring

### Flower Dashboard

Access the Celery monitoring dashboard:
```
http://localhost:5555
```

Features:
- Task execution history
- Worker status
- Queue monitoring
- Task statistics

### Logs

```bash
# API server logs
docker-compose logs api

# Celery worker logs
docker-compose logs celery-worker

# Redis logs
docker-compose logs redis

# Follow logs
docker-compose logs -f
```

## Error Handling

### Automatic Retries

Tasks automatically retry on:
- ConnectionError
- TimeoutError
- Custom configurable exceptions

Retry strategy:
- Max 3 retries
- 30s initial delay
- Exponential backoff with jitter
- Max 120s delay between retries

### Dead Letter Queue

Failed tasks after max retries go to the DLQ for manual inspection:
```bash
celery -A celery_app inspect active_queues
```

## Database Schema

### Job Store (SQLite)

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  doc_id_a TEXT NOT NULL,
  doc_id_b TEXT NOT NULL,
  status TEXT NOT NULL,
  current_segment INTEGER,
  progress_pct REAL,
  error_message TEXT,
  result_data TEXT,
  celery_task_id TEXT,
  created_at TEXT,
  started_at TEXT,
  completed_at TEXT,
  updated_at TEXT
);
```

## Performance Tuning

### For Development
```yaml
# Single worker, single concurrency
celery-worker:
  command: celery -A celery_app worker --loglevel=info --concurrency=1
```

### For Production
```yaml
# Multiple workers with concurrency
celery-worker:
  command: celery -A celery_app worker --loglevel=warning --concurrency=4
  deploy:
    replicas: 3
```

## Troubleshooting

### Jobs Not Processing

1. Check Redis is running: `redis-cli ping` (should return PONG)
2. Check Celery worker is running: `ps aux | grep celery`
3. Check Celery logs: `docker-compose logs celery-worker`

### WebSocket Connection Issues

1. Ensure API server is running on correct port
2. Check WebSocket URL is correct in browser console
3. Verify CORS settings in FastAPI

### High Memory Usage

1. Increase worker prefetch multiplier (default: 1)
2. Reduce result backend TTL (default: 86400s)
3. Scale to more workers with lower concurrency

## Future Enhancements

1. **Priority Queues**: Premium users get faster processing
2. **Task Batching**: Process multiple PDFs in parallel
3. **Result Caching**: Cache segment outputs for identical documents
4. **Monitoring**: Prometheus metrics + Grafana dashboards
5. **Database Migration**: SQLite → PostgreSQL for concurrent writes
6. **Redis Cluster**: High availability for production
7. **Task Retries with Exponential Backoff**: Already implemented
8. **Dead Letter Queues**: Already configured

## References

- [Celery Documentation](https://docs.celeryproject.org/)
- [Redis Documentation](https://redis.io/documentation)
- [Flower Monitoring](https://flower.readthedocs.io/)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
