// §10.5 알림 어댑터. 앱 전환 시 FcmAdapter(Capacitor Push Notifications)만 추가하면 화면 코드는 그대로.
import { api, post } from "./api";

export type Payload = { title: string; body: string; url?: string };

export interface NotificationAdapter {
  requestPermission(): Promise<boolean>;
  getToken(): Promise<string>;
  onMessage(cb: (p: Payload) => void): void;
}

const b64ToBytes = (b64: string) => {
  const s = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
};

export const WebPushAdapter: NotificationAdapter = {
  async requestPermission() {
    return "serviceWorker" in navigator && (await Notification.requestPermission()) === "granted";
  },
  async getToken() {
    const reg = await navigator.serviceWorker.ready;
    const key = await api<string>("/push/vapid-public-key");
    const sub =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) }));
    return JSON.stringify(sub);
  },
  onMessage(cb) {
    navigator.serviceWorker.addEventListener("message", (e) => cb(e.data));
  },
};

export const notifications: NotificationAdapter = WebPushAdapter;

/** 권한 요청 → 토큰 → 서버 등록. iOS는 홈화면에 추가한 뒤에만 동작한다. */
export async function enableNotifications(quietStart = 23, quietEnd = 7) {
  if (!(await notifications.requestPermission())) return false;
  const sub = JSON.parse(await notifications.getToken());
  await post("/push/subscribe", { ...sub, quiet_start: quietStart, quiet_end: quietEnd });
  return true;
}
