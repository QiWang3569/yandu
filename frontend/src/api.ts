import { notificationsChanged } from "./notificationEvents";

export type User = {
  id: string;
  nickname: string;
  campus: string;
  role: string;
  email?: string | null;
  email_notifications: boolean;
  has_password?: boolean;
  bio?: string;
  avatar_color?: "sage" | "blue" | "peach" | "lavender";
};
export type Item = {
  id: string;
  title: string;
  description: string;
  category: string;
  price: number;
  campus: string;
  condition_grade: string;
  tags: string[];
  images: string[];
  art: string;
  status: string;
  seller: User;
  created_at: string;
  expires_at: string | null;
  is_favorite: boolean;
  is_owner: boolean;
  is_demo: boolean;
  sale_feedback_count: number;
  can_relist?: boolean;
  can_withdraw?: boolean;
  can_duplicate?: boolean;
};
export type ItemDraft = {
  id: string;
  raw: string;
  title: string | null;
  description: string | null;
  category: string | null;
  price: number | null;
  campus: string;
  condition_grade: string;
  tags: string[];
  images: string[];
  clarification: string | null;
  created_at: string;
  updated_at: string;
};
export type Meta = {
  categories: string[];
  campuses: string[];
  conditions: string[];
  demo_mode: boolean;
  ai_mode: string;
  embedding_mode: string;
  active_items: number;
  email_auth_ready: boolean;
  chat_email_ready: boolean;
  vision_enabled: boolean;
};
export type ChatMessage = {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  images: string[];
  created_at: string;
  read_at: string | null;
  hidden: boolean;
};
export type Conversation = {
  id: string;
  item_id: string;
  buyer_id: string;
  seller_id: string;
  item_title: string;
  item_status: string;
  item_image: string | null;
  counterpart: User;
  last_message: ChatMessage | null;
  unread_count: number;
  updated_at: string;
  blocked: boolean;
  blocked_by_me: boolean;
  deal_status: "NONE" | "REQUESTED" | "RESERVED" | "DECLINED" | "CANCELED" | "SOLD" | "CONFIRMED";
};
export type Parsed = {
  category: string | null;
  max_price: number | null;
  campus: string;
  keywords: string[];
  excluded_keywords: string[];
  preferences: string[];
  condition_grade: string | null;
  clarification: string | null;
  around_price?: boolean;
};
export type SmartSearchResult = {
  parsed: Parsed;
  items: Item[];
  total: number;
  page: number;
  size: number;
};
export type ParsedItem = {
  title: string | null;
  description: string | null;
  category: string | null;
  price: number | null;
  campus: string;
  condition_grade: string;
  tags: string[];
  clarification: string | null;
};
export type ParsedWanted = {
  title: string | null;
  description: string | null;
  category: string | null;
  budget: number | null;
  campus: string;
  clarification: string | null;
};
export type Intent = Parsed & {
  id: string;
  raw_query: string;
  status: string;
  match_count: number;
  created_at: string;
  expires_at: string | null;
  wanted_id: string | null;
  wanted_status: string | null;
  matching_mode: string;
  matching_state: "PENDING" | "RUNNING" | "DONE" | "FAILED";
  completed_item_id: string | null;
};

export type ChatReport = {
  id: string;
  reason: string;
  status: string;
  created_at: string;
  item_title: string;
  message_id: string;
  message_body: string;
  message_images: string[];
  sender: User;
};
export type Notice = {
  id: string;
  intent_id: string;
  item: Item;
  score: number;
  reason: string;
  verdict: "MATCH" | "UNCERTAIN";
  questions: string[];
  evidence: { criterion: string; quote: string }[];
  review_mode: string;
  score_kind: string;
  is_read: boolean;
  available: boolean;
  created_at: string;
};
export type SaleFeedbackNotice = {
  id: string;
  item: Item;
  reporter: User;
  created_at: string;
  is_read: boolean;
};
export type Announcement = {
  id: string;
  title: string;
  body: string;
  kind: "公告" | "更新";
  created_at: string;
  is_read?: boolean | null;
};
export type AdminAnnouncement = Announcement & {
  active: boolean;
};
export type Wanted = {
  id: string;
  title: string;
  description: string;
  category: string | null;
  budget: number | null;
  campus: string;
  buyer: User;
  is_owner: boolean;
  status: string;
  created_at: string;
  expires_at: string | null;
  intent: Intent | null;
};
export type Report = {
  id: string;
  item: Item;
  reason: string;
  risk: string;
  evidence: string[];
  status: string;
  created_at: string;
};
export type Log = {
  id: string;
  action: string;
  actor: User;
  target_id: string;
  detail: string;
  created_at: string;
};
export type TradeReview = {
  id: string;
  conversation_id: string;
  item_id: string;
  item_title: string;
  reviewer_id: string;
  reviewee_id: string;
  reviewer: Pick<User, "id" | "nickname" | "campus" | "role"> | null;
  rating: number;
  body: string;
  tags: string[];
  created_at: string;
};
export type ReviewSummary = {
  average: number | null;
  count: number;
  distribution: { rating: number; count: number }[];
};
export type UserReviews = {
  user: Pick<User, "id" | "nickname" | "campus" | "role">;
  summary: ReviewSummary;
  reviews: TradeReview[];
};
export type AdminSummary = {
  reports: number;
  chat_reports: number;
  feedback: number;
  announcements: number;
  pending_total: number;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
let authRevision = 0;

export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const requestAuthRevision = authRevision;
  const response = await fetch("/api/v1" + path, {
    method,
    signal,
    credentials: "include",
    ...(data instanceof FormData
      ? { body: data }
      : data !== undefined
        ? {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          }
        : {}),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/") && requestAuthRevision === authRevision) {
      window.dispatchEvent(new Event("yandu-session-expired"));
    }
    const detail = result?.detail;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((d: { msg: string }) => d.msg.replace("Value error, ", ""))
              .join("；")
          : "服务连接失败，请稍后重试", response.status,
    );
  }
  if (method === "POST" && ["/auth/refresh", "/auth/demo", "/auth/email/verify", "/auth/password/login", "/auth/password/set", "/auth/logout"].includes(path)) authRevision++;
  if (method !== "GET" && /\/(?:notifications|conversations|feedback|sale-feedback|announcements)(?:\/|$)/.test(path)) notificationsChanged();
  return result as T;
}
export const money = (n: number) =>
  n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
export const campusShort = (v: string) =>
  v.replace("校本部", "").replace("学区", "").replace("新校区", "");
export const statusText: Record<string, string> = {
  ACTIVE: "在售",
  RESERVED: "已预订",
  SOLD: "已售出",
  EXPIRED: "已过期",
  BANNED: "审核隐藏",
  WITHDRAWN: "已撤回",
  PAUSED: "已暂停",
  COMPLETED: "已结束",
};
export function ago(date: string) {
  const hours = Math.max(0, (Date.now() - new Date(date).getTime()) / 3600000);
  return hours < 1
    ? "刚刚发布"
    : hours < 24
      ? `${Math.floor(hours)} 小时前`
      : `${Math.floor(hours / 24)} 天前`;
}
