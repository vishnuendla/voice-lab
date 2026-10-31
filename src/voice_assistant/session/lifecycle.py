"""Wrapping up a finished session, in one place.

`run_pipeline` calls this from its `finally` so a dropped socket still gets a
summary; the browser's Disconnect calls it early, while the transport is still
open, so the summary can be shown. Both paths run, so it is idempotent.
"""

from __future__ import annotations

import logging

from voice_assistant.session.recall import store_session_recall

logger = logging.getLogger("voice_assistant.session")


async def end_session(store, persist=None, *, close: bool = True) -> str:
    """Flush pending turns, summarize, and optionally close. Returns the summary.

    Never raises -- the conversation is already over, and nothing here is worth
    failing a disconnect for.
    """
    if store is None:
        return ""
    try:
        if not store.ended:
            store.ended = True
            if persist is not None:
                await persist.flush()
            store.summary = await store_session_recall(store)
        if close:
            # A plain UPDATE, so calling this again after an early summary is fine.
            await store.close()
        return store.summary
    except Exception:
        logger.exception("could not finish the session cleanly")
        return store.summary
