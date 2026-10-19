import asyncio
import logging
from typing import Coroutine, Set

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()

    def run_task(self, coro: Coroutine, name: str = None) -> asyncio.Task:
        """
        Safely spawn a coroutine in the background, keeping a strong reference
        to prevent immediate garbage collection, and removing it upon completion.
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        
        def _done_callback(t: asyncio.Task):
            self._tasks.discard(t)
            try:
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.error(f"Background task '{t.get_name()}' failed: {exc}", exc_info=exc)
            except Exception as e:
                logger.error(f"Error in background task cleanup callback: {e}")

        task.add_done_callback(_done_callback)
        return task

    async def cancel_all(self):
        """Cancel and clean up all active background tasks."""
        if not self._tasks:
            return
        
        logger.info(f"Cancelling {len(self._tasks)} background tasks...")
        for task in list(self._tasks):
            task.cancel()
            
        try:
            await asyncio.wait(list(self._tasks), timeout=3.0)
        except Exception as e:
            logger.error(f"Error awaiting cancelled background tasks: {e}")
            
        self._tasks.clear()
        logger.info("All background tasks cleaned up.")

background_task_manager = BackgroundTaskManager()
