"""WebSocket server for real-time job progress updates.

Provides WebSocket endpoints that subscribe to Redis pubsub channels
for streaming progress updates to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ucc.storage.job_store import JobStore, JobStatus


# Redis connection pool for async operations
_redis_pool: Optional[aioredis.ConnectionPool] = None


async def get_redis_client() -> aioredis.Redis:
    """Get async Redis client for pubsub."""
    global _redis_pool
    
    if _redis_pool is None:
        redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        _redis_pool = aioredis.ConnectionPool.from_url(redis_url)
    
    return aioredis.Redis(connection_pool=_redis_pool)


class ConnectionManager:
    """Manages WebSocket connections for job progress updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, list[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept connection and register for job updates."""
        await websocket.accept()
        
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        
        self.active_connections[job_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, job_id: str):
        """Unregister connection."""
        if job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            
            # Clean up empty lists
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
    
    async def send_progress(self, job_id: str, data: Dict[str, Any]):
        """Send progress update to all connections for a job."""
        if job_id not in self.active_connections:
            return
        
        disconnected = []
        
        for websocket in self.active_connections[job_id]:
            try:
                await websocket.send_json(data)
            except Exception:
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            self.disconnect(websocket, job_id)


# Global connection manager
manager = ConnectionManager()


async def job_progress_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for job progress updates.
    
    Subscribes to Redis pubsub channel for the job and streams
    progress updates to the client.
    
    Args:
        websocket: FastAPI WebSocket connection
        job_id: Job identifier to subscribe to
    """
    # Check if job exists
    job_store = JobStore()
    job = job_store.get(job_id)
    
    if job is None:
        await websocket.close(code=4404, reason="Job not found")
        return
    
    # Accept connection
    await manager.connect(websocket, job_id)
    
    # Send initial status
    try:
        await websocket.send_json({
            "type": "initial",
            "job_id": job_id,
            "status": job.status.value,
            "current_segment": job.current_segment,
            "current_segment_name": job.current_segment_name,
            "progress_pct": round(job.progress_pct, 1),
            "total_segments": job.total_segments,
        })
    except Exception:
        manager.disconnect(websocket, job_id)
        return
    
    # If already completed, send final status and close
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        try:
            await websocket.send_json({
                "type": "final",
                "job_id": job_id,
                "status": job.status.value,
                "error_message": job.error_message,
            })
            await websocket.close()
        except Exception:
            pass
        finally:
            manager.disconnect(websocket, job_id)
        return
    
    # Subscribe to Redis pubsub for live updates
    redis_client = await get_redis_client()
    pubsub = redis_client.pubsub()
    
    try:
        channel = f"job:{job_id}"
        await pubsub.subscribe(channel)
        
        # Listen for messages
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    data["type"] = "progress"
                    await websocket.send_json(data)
                    
                    # Check if job is complete
                    if data.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                        await websocket.close()
                        break
                        
                except json.JSONDecodeError:
                    continue
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        manager.disconnect(websocket, job_id)


async def broadcast_progress(job_id: str, data: Dict[str, Any]):
    """Broadcast progress update to all connected clients for a job.
    
    Called by tasks/callbacks.py after updating Redis pubsub.
    This is an alternative direct broadcast method.
    
    Args:
        job_id: Job identifier
        data: Progress data to broadcast
    """
    await manager.send_progress(job_id, data)


def setup_websocket_routes(app):
    """Register WebSocket routes with FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    @app.websocket("/ws/jobs/{job_id}")
    async def ws_job_progress(websocket: WebSocket, job_id: str):
        await job_progress_websocket(websocket, job_id)
    
    @app.websocket("/ws/health")
    async def ws_health(websocket: WebSocket):
        """Health check endpoint for WebSocket connectivity."""
        await websocket.accept()
        await websocket.send_json({"status": "ok"})
        await websocket.close()
