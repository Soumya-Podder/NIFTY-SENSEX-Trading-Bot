from datetime import datetime,timezone
class CircuitBreaker:
    def __init__(self): self.halted=False; self.reason=None; self.since=None
    def trip(self,reason):
        self.halted=True; self.reason=reason; self.since=datetime.now(timezone.utc).isoformat()
    def reset(self): self.halted=False; self.reason=None; self.since=None
