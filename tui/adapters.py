import threading
from typing import Callable, Optional, Any, Iterable


ProgressCb = Callable[[str, int, Optional[int]], None]


def run_in_thread(target: Callable[..., Any], *args, **kwargs) -> threading.Thread:
    th = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    th.start()
    return th


def run_analysis_in_thread(
    run_callable: Callable[[dict, ProgressCb, threading.Event], Any],
    args: dict,
    progress_cb: Optional[ProgressCb] = None,
    cancel_event: Optional[threading.Event] = None,
) -> threading.Thread:
    if progress_cb is None:
        progress_cb = lambda *_: None  # no-op
    if cancel_event is None:
        cancel_event = threading.Event()

    def _runner():
        run_callable(args, progress_cb, cancel_event)  # type: ignore[misc]

    return run_in_thread(_runner)


def truncate_rows(rows: Iterable[Any], limit: int = 200) -> list:
    out = []
    for i, r in enumerate(rows):
        if i >= limit:
            break
        out.append(r)
    return out
