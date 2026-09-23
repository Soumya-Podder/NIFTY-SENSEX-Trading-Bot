"""Optional, non-blocking Telegram notifications for the paper account."""
import queue
import threading
from datetime import datetime
import httpx


class TelegramNotifier:
    def __init__(self, token="", chat_id="", enabled=False, timeout=10):
        self.token=str(token or "").strip(); self.chat_id=str(chat_id or "").strip()
        self.enabled=bool(enabled); self.timeout=timeout
        self.queue=queue.Queue(maxsize=100); self.thread=None; self.stop_event=threading.Event()
        self.sent=0; self.dropped=0; self.last_sent_at=None; self.last_error=None

    @property
    def configured(self): return bool(self.token and self.chat_id)

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.thread=threading.Thread(target=self._run,name="telegram-notifier",daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)

    def notify(self, message):
        if not self.enabled or not self.configured: return False
        try: self.queue.put_nowait(str(message)[:4000]); return True
        except queue.Full: self.dropped+=1; return False

    def _run(self):
        while not self.stop_event.is_set():
            try: message=self.queue.get(timeout=.5)
            except queue.Empty: continue
            try:
                response=httpx.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                    data={"chat_id":self.chat_id,"text":message,"disable_web_page_preview":True},timeout=self.timeout)
                response.raise_for_status(); self.sent+=1
                self.last_sent_at=datetime.now().astimezone().isoformat(); self.last_error=None
            except Exception as exc:
                # Never retain response bodies or URLs because they may contain credentials.
                self.last_error=type(exc).__name__
            finally: self.queue.task_done()

    def status(self):
        return {"enabled":self.enabled,"configured":self.configured,
            "worker_alive":bool(self.thread and self.thread.is_alive()),"queued":self.queue.qsize(),
            "sent":self.sent,"dropped":self.dropped,"last_sent_at":self.last_sent_at,
            "last_error":self.last_error}
