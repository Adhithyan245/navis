import asyncio
import logging
from typing import Dict, Any, Optional
from apps.api.services.behavior_storage import IBehaviorStorage, SQLAlchemyBehaviorStorage
from apps.api.core.background import background_task_manager

logger = logging.getLogger(__name__)

class BehaviorEventQueue:
    def __init__(self, storage: IBehaviorStorage):
        # Bounded: under overload, analytics events are dropped, never requests.
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
        self._storage: IBehaviorStorage = storage
        self._worker_task: Optional[asyncio.Task] = None

    def start(self):
        """Start the background queue worker under the BackgroundTaskManager."""
        if self._worker_task is None:
            self._worker_task = background_task_manager.run_task(
                self._worker_loop(), name="behavior_queue_worker"
            )
            logger.info("BehaviorEventQueue background worker started successfully.")

    async def _worker_loop(self):
        """Worker loop that drains the queue and handles DB writes safely."""
        while True:
            try:
                event = await self._queue.get()
                if event is None:  # Sentinel to stop the worker
                    self._queue.task_done()
                    break

                event_type = event.get("type")
                payload = event.get("payload", {})

                try:
                    if event_type == "interaction":
                        await self._storage.save_interaction(
                            user_id=payload["user_id"],
                            action_type=payload["action_type"],
                            item_id=payload.get("item_id"),
                            item_type=payload.get("item_type"),
                            domain=payload.get("domain"),
                            city=payload.get("city"),
                            query=payload.get("query"),
                            item_categories=payload.get("item_categories")
                        )
                    elif event_type == "memory_update":
                        await self._storage.update_context_memory(
                            user_id=payload["user_id"],
                            search_entry=payload.get("search_entry"),
                            domain=payload.get("domain"),
                            location=payload.get("location")
                        )
                    elif event_type == "audit_log":
                        await self._storage.save_audit_log(
                            user_id=payload.get("user_id"),
                            endpoint=payload["endpoint"],
                            live_apis_used=payload["live_apis_used"],
                            db_queries_used=payload["db_queries_used"],
                            fallback_triggers=payload["fallback_triggers"]
                        )
                except Exception as e:
                    # Robust isolation: database failure does not impact other events
                    logger.error(f"Failed to persist behavior event {event_type} inside worker: {e}", exc_info=True)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("Behavior queue worker cancelled.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in behavior queue worker: {e}", exc_info=True)
                await asyncio.sleep(1)  # Throttling fallback

    def enqueue_interaction(
        self, user_id: int, action_type: str,
        item_id: Optional[str] = None, item_type: Optional[str] = None,
        domain: Optional[str] = None, city: Optional[str] = None,
        query: Optional[str] = None, item_categories: Optional[list] = None
    ):
        """Enqueue a user interaction event to be saved in the background."""
        event = {
            "type": "interaction",
            "payload": {
                "user_id": user_id,
                "action_type": action_type,
                "item_id": item_id,
                "item_type": item_type,
                "domain": domain,
                "city": city,
                "query": query,
                "item_categories": item_categories
            }
        }
        self._offer(event)

    def enqueue_memory_update(
        self, user_id: int,
        search_entry: Optional[dict] = None,
        domain: Optional[str] = None,
        location: Optional[dict] = None
    ):
        """Enqueue a context memory update event to be processed in the background."""
        event = {
            "type": "memory_update",
            "payload": {
                "user_id": user_id,
                "search_entry": search_entry,
                "domain": domain,
                "location": location
            }
        }
        self._offer(event)

    def enqueue_audit_log(
        self, user_id: Optional[int], endpoint: str,
        live_apis_used: dict, db_queries_used: list,
        fallback_triggers: list
    ):
        """Enqueue a source audit log to be saved in the background."""
        event = {
            "type": "audit_log",
            "payload": {
                "user_id": user_id,
                "endpoint": endpoint,
                "live_apis_used": live_apis_used,
                "db_queries_used": db_queries_used,
                "fallback_triggers": fallback_triggers
            }
        }
        self._offer(event)

    def _offer(self, event: dict) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def stop(self):
        """Gracefully stop the worker, draining pending tasks first."""
        if self._worker_task:
            self._queue.put_nowait(None)  # Enqueue EOF marker
            await self._queue.join()
            self._worker_task = None

# Initialize global singleton behavior queue
storage_instance = SQLAlchemyBehaviorStorage()
behavior_queue = BehaviorEventQueue(storage_instance)
