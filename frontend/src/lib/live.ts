"use client";
// §10.4 WS는 갱신 신호, 원천은 REST. 받은 값으로 query cache를 고치고, 재연결 시 REST를 다시 불러 공백을 메운다.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { type Current, type LiveMessage, type ProbeReading, wsUrl } from "./api";

export function useLive(deviceId?: string) {
  const qc = useQueryClient();

  useEffect(() => {
    let ws: WebSocket;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(wsUrl(deviceId));
      ws.onopen = () => {
        if (retry > 0) qc.invalidateQueries(); // 끊긴 동안의 공백 메우기
        retry = 0;
      };
      ws.onmessage = (e) => {
        const msg: LiveMessage = JSON.parse(e.data);
        if (msg.type === "reading") {
          const { type: _, ...current } = msg;
          qc.setQueryData<Current>(["current", msg.device_id], current);
          qc.setQueryData<ProbeReading[]>(["series", msg.device_id, "24h"], (old) =>
            old ? [...old, ...msg.probes] : old,
          );
        } else {
          qc.setQueryData<Current>(["current", msg.device_id], (old) => old && { ...old, state: msg.state });
          qc.invalidateQueries({ queryKey: ["devices"] });
          qc.invalidateQueries({ queryKey: ["events", msg.device_id] });
        }
      };
      ws.onclose = () => {
        if (closed) return;
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** retry++)); // 지수 백오프
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws.close();
    };
  }, [deviceId, qc]);
}
