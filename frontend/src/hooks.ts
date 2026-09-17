import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AgentEvent } from "./api";

/** Muat data lalu ulangi setiap `interval` ms selama tab terlihat. */
export function usePoll<T>(load: (() => Promise<T>) | null, interval: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = useCallback(async () => {
    if (!loadRef.current) return;
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    setData(null);
    if (!load) return;
    refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, interval);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, refresh };
}

/** Aliran event agen (SSE) dengan riwayat awal dari buffer server. */
export function useEvents(limit = 300) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let closed = false;
    api.recentEvents().then((initial) => !closed && setEvents(initial.slice(-limit))).catch(() => undefined);
    const source = new EventSource("/api/events");
    source.onopen = () => setLive(true);
    source.onerror = () => setLive(false);
    source.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as AgentEvent;
      setEvents((prev) => (prev.some((e) => e.id === event.id) ? prev : [...prev.slice(-(limit - 1)), event]));
    };
    return () => {
      closed = true;
      source.close();
    };
  }, [limit]);

  return { events, live };
}
