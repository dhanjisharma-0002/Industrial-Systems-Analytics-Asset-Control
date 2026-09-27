import { useState, useEffect, useRef, useCallback } from "react";

/**
 * Custom React hook for subscribing to ISAAC live telemetry and prediction stream via WebSocket.
 * Features:
 * - Resilient auto-reconnect with exponential backoff
 * - Connection status tracking (CONNECTED, CONNECTING, DISCONNECTED, ERROR)
 * - Heartbeat ping-pong to keep connection alive
 * - Live update timestamp & payload state
 * - Optional custom message listener callback
 */
export function useTelemetryWebSocket(onMessageCallback) {
  const [connectionStatus, setConnectionStatus] = useState("CONNECTING"); // CONNECTED | CONNECTING | RECONNECTING | DISCONNECTED | ERROR
  const [latestPayload, setLatestPayload] = useState(null);
  const [lastTimestamp, setLastTimestamp] = useState(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const isUnmountedRef = useRef(false);
  const callbackRef = useRef(onMessageCallback);

  // Keep callback reference updated
  useEffect(() => {
    callbackRef.current = onMessageCallback;
  }, [onMessageCallback]);

  const getWebSocketUrl = () => {
    if (import.meta.env.VITE_WS_URL) {
      return import.meta.env.VITE_WS_URL;
    }
    const rawApiUrl = import.meta.env.VITE_API_BASE_URL;
    if (rawApiUrl) {
      const wsBase = rawApiUrl.replace(/\/$/, "").replace(/^http/, "ws");
      return `${wsBase}/ws/telemetry`;
    }
    if (typeof window !== "undefined") {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${window.location.host}/ws/telemetry`;
    }
    return "ws://127.0.0.1:8000/ws/telemetry";
  };

  const connect = useCallback(() => {
    if (isUnmountedRef.current) return;

    // Clean up any existing socket
    if (socketRef.current) {
      try {
        socketRef.current.close();
      } catch {
        // ignore close error
      }
    }

    const wsUrl = getWebSocketUrl();
    console.log("[WS] connecting to", wsUrl);
    setConnectionStatus((prev) => (reconnectCount > 0 ? "RECONNECTING" : "CONNECTING"));

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (isUnmountedRef.current) return;
        console.log("[WS] connected");
        setConnectionStatus("CONNECTED");
        setReconnectCount(0);

        // Start heartbeat ping every 20 seconds
        if (heartbeatIntervalRef.current) clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "PING" }));
          }
        }, 20000);
      };

      ws.onmessage = (event) => {
        if (isUnmountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          console.log("[WS] message received", data.type, data.machine_id || "");
          if (data.type === "PONG") return; // Keepalive ack

          const now = new Date();
          setLastTimestamp(now);
          setLatestPayload(data);

          if (callbackRef.current && typeof callbackRef.current === "function") {
            callbackRef.current(data);
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onerror = (err) => {
        if (isUnmountedRef.current) return;
        console.warn("WebSocket connection error:", err);
        setConnectionStatus("ERROR");
      };

      ws.onclose = () => {
        if (isUnmountedRef.current) return;
        console.log("[WS] disconnected");
        setConnectionStatus("DISCONNECTED");
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }

        // Schedule auto-reconnect with exponential backoff (1s -> 2s -> 4s -> max 10s)
        const delay = Math.min(10000, 1000 * Math.pow(1.5, reconnectCount));
        setReconnectCount((c) => c + 1);
        console.log(`[WS] reconnecting in ${delay}ms`);

        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    } catch (err) {
      console.error("Error creating WebSocket instance:", err);
      setConnectionStatus("DISCONNECTED");
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 3000);
    }
  }, [reconnectCount]);

  useEffect(() => {
    isUnmountedRef.current = false;
    connect();

    return () => {
      isUnmountedRef.current = true;
      if (heartbeatIntervalRef.current) clearInterval(heartbeatIntervalRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current) {
        try {
          socketRef.current.close();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  return {
    connectionStatus,
    latestPayload,
    lastTimestamp,
    reconnectCount,
    reconnect: connect,
  };
}
