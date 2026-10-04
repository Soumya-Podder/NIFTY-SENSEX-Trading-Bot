type Data = Record<string, any>;

export async function api(path: string, body?: Data, signal?: AbortSignal, timeoutMs = 30000) {
 const deadline = AbortSignal.timeout(timeoutMs);
 const requestSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
 const response = await fetch(`/api${path}`, {
  method: body ? "POST" : "GET",
  headers: body ? { "Content-Type": "application/json" } : undefined,
  body: body ? JSON.stringify(body) : undefined,
  signal: requestSignal,
 });
 let payload;
 try {
  payload = await response.json();
 } catch {
  requestSignal.throwIfAborted();
  throw new Error(`Request to ${path} failed (HTTP ${response.status}): the backend returned an unreadable response. Check the backend and retry.`);
 }
 if (!response.ok)
  throw new Error(
   typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload),
  );
 return payload;
}
