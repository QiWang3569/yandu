import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowDownUp,
  ArrowRight,
  Bell,
  Bike,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Compass,
  Flag,
  Heart,
  LayoutGrid,
  Leaf,
  LogOut,
  Mail,
  MapPin,
  Monitor,
  Moon,
  Pause,
  Play,
  Plus,
  ShieldCheck,
  Shirt,
  Sparkles,
  Sprout,
  Sun,
  Upload,
  Users,
  X,
  Lamp,
  Copy,
  Share2,
  RefreshCw,
  CheckCheck,
  MessageCircle,
  UserRound,
} from "lucide-react";
import {
  api,
  type User,
  type Item,
  type ItemDraft,
  type Meta,
  type Intent,
  type Parsed,
  type SmartSearchResult,
  type Notice,
  type AdminAnnouncement,
  type SaleFeedbackNotice,
  type Wanted,
  type Report,
  type ChatReport,
  type Log,
  type Conversation,
  type AdminSummary,
  money,
  campusShort,
  statusText,
} from "./api";
import {
  Brand,
  Busy,
  Card,
  Empty,
  Intro,
  Modal,
  ProductArt,
} from "./components";
import { IntentForm, PublishForm, PublishWorkspace, WantedForm } from "./forms";
import { AuthMethods, ChatCenter, PasswordSetup } from "./AccountAndChat";
import { ProfileHome, ProfileNav, type PersonalView } from "./Profile";
import { SearchBar } from "./SearchBar";
import { FeedbackCenter, FeedbackWorkspace, type FeedbackNotices } from "./Feedback";
import { AnnouncementFeed } from "./AnnouncementFeed";
import { ProductGallery } from "./ProductGallery";
import { SellerRating, UserReviewsPanel } from "./Reviews";
import { listenForNotificationChanges, notificationVersion } from "./notificationEvents";
import { useSessionRenewal } from "./session";
import { SessionRecovery } from "./SessionRecovery";

import { AdminMetrics, type BusinessOverviewData } from "./AdminMetrics";

const nav = [
  { key: "market", label: "逛逛校园", icon: Compass },
  { key: "wanted", label: "求购看板", icon: Sprout },
  { key: "intents", label: "我的代蹲", icon: Sparkles },
  { key: "profile", label: "我的主页", icon: UserRound },
];
type View = "market" | "profile" | "intents" | "messages" | "wanted" | "favorites" | "mine" | "mywanted" | "admin" | "admin-chat" | "admin-reports" | "admin-logs" | "admin-feedback" | "admin-metrics";
type ModalName =
  | "login"
  | "intent"
  | "publish"
  | "wanted"
  | "notifications"
  | "compare"
  | "detail"
  | "reviews"
  | "announcements"
  | "feedback"
  | null;
const validViews = [
  "market",
  "profile",
  "intents",
  "messages",
  "wanted",
  "favorites",
  "mine",
  "mywanted",
  "admin",
  "admin-metrics",
  "admin-chat",
  "admin-reports",
  "admin-logs",
  "admin-feedback",
];
function currentView(): View {
  const v = location.hash.slice(1).split("/")[0];
  return (validViews.includes(v) ? v : "market") as View;
}
function currentConversation(): string | null {
  const match = /^#messages\/([A-Za-z0-9_-]+)$/.exec(location.hash);
  return match?.[1] ?? null;
}

function initialTheme(): "light" | "dark" {
  let saved: string | null = null;
  try { saved = localStorage.getItem("yandu-theme"); } catch { /* Storage may be disabled. */ }
  const theme = saved === "light" || saved === "dark" ? saved :
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  return theme;
}

function useResource<T>(
  url: string,
  revision: number,
  enabled = true,
  poll = false,
  identity = "",
) {
  const [data, setData] = useState<T | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const resourceKey = useRef("");
  useEffect(() => {
    let alive = true;
    let sequence = 0;
    const key = `${url}:${identity}`;
    if (resourceKey.current !== key || !enabled) setData(null);
    resourceKey.current = key;
    setError("");
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const read = () => {
      const request = ++sequence, epoch = notificationVersion();
      void api<T>(url)
      .then((d) => {
        if (alive && request === sequence && (!identity || epoch === notificationVersion())) { setData(d); setError(""); }
      })
      .catch((e) => {
        if (alive && request === sequence) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    };
    read();
    const timer = poll
      ? window.setInterval(() => { if (document.visibilityState === "visible") read(); }, 10000)
      : undefined;
    return () => {
      alive = false;
      if (timer !== undefined) clearInterval(timer);
    };
  }, [url, revision, enabled, poll, identity]);
  return { data, loading, error };
}

export default function App() {
  const [notificationRevision, setNotificationRevision] = useState(0);
  useEffect(() => listenForNotificationChanges(() => setNotificationRevision((n) => n + 1)), []);
  const [feedbackId, setFeedbackId] = useState<string | null>(null);
  const feedbackAfterLogin = useRef(false);
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);
  const [meta, setMeta] = useState<Meta | null>(null),
    [user, setUser] = useState<User | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [recoverSession, setRecoverSession] = useState(false);
  const [sessionEpoch, setSessionEpoch] = useState(0);
  useSessionRenewal(user?.id, setSessionExpired, sessionEpoch);
  const [view, setView] = useState<View>(currentView),
    [revision, setRevision] = useState(0);
  const [modal, setModal] = useState<ModalName>(null),
    [toast, setToast] = useState(""),
    [busy, setBusy] = useState(false);
  const [fatal, setFatal] = useState(""),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState("");
  const [category, setCategory] = useState(""),
    [campus, setCampus] = useState(""),
    [price, setPrice] = useState(""),
    [sort, setSort] = useState("recommended"),
    [page, setPage] = useState(1),
    [onSale, setOnSale] = useState(true);
  const [intentQuery, setIntentQuery] = useState(""),
    [selected, setSelected] = useState<Item | null>(null),
    [compare, setCompare] = useState<Item[]>([]);
  const [similar, setSimilar] = useState<Item[]>([]);
  const [editingItem, setEditingItem] = useState<Item | null>(null);
  const [detailFromChat, setDetailFromChat] = useState(false);
  const [copiedDraft, setCopiedDraft] = useState<ItemDraft | null>(null);
  const [editingWanted, setEditingWanted] = useState<Wanted | null>(null);
  const [editingIntent, setEditingIntent] = useState<Intent | null>(null);
  const [publishingIntent, setPublishingIntent] = useState<Intent | null>(null);
  const [pendingConversation, setPendingConversation] = useState(currentConversation);
  const consumeConversation = useCallback(() => setPendingConversation(null), []);
  const [prefill, setPrefill] = useState<Wanted | null>(null);
  const [noticeIntent, setNoticeIntent] = useState<Intent | null>(null);
  const [chatItem, setChatItem] = useState<Item | null>(null),
    [chatDraft, setChatDraft] = useState("");
  const [avatarMenu, setAvatarMenu] = useState(false);
  const [editProfile, setEditProfile] = useState(false);
  const [reporting, setReporting] = useState(false),
    [reportText, setReportText] = useState("");
  const [searchRequest, setSearchRequest] = useState(0);
  const [smartMode, setSmartMode] = useState(false);
  const [smartQuery, setSmartQuery] = useState("");
  const [smartPage, setSmartPage] = useState(1);
  const [smartResult, setSmartResult] = useState<SmartSearchResult | null>(null);
  const [smartBusy, setSmartBusy] = useState(false);
  const [smartError, setSmartError] = useState("");
  const [smartRequest, setSmartRequest] = useState(0);
  const marketRef = useRef<HTMLElement>(null);
  const avatarMenuRef = useRef<HTMLDivElement>(null);
  const reportRef = useRef<HTMLTextAreaElement>(null);
  const categoryTabsRef = useRef<HTMLDivElement>(null);
  const categoryDrag = useRef({ active: false, startX: 0, startLeft: 0, moved: false });
  const sidebarNavRef = useRef<HTMLElement>(null);
  const sidebarNavDrag = useRef({ active: false, startX: 0, startLeft: 0, moved: false });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem("yandu-theme", theme); } catch { /* Keep the current choice for this visit. */ }
  }, [theme]);

  function categoryDown(e: React.PointerEvent<HTMLDivElement>) {
    const el = categoryTabsRef.current;
    if (!el) return;
    categoryDrag.current = { active: true, startX: e.clientX, startLeft: el.scrollLeft, moved: false };
  }
  function categoryMove(e: React.PointerEvent<HTMLDivElement>) {
    const el = categoryTabsRef.current;
    const d = categoryDrag.current;
    if (!el || !d.active) return;
    const dx = e.clientX - d.startX;
    if (Math.abs(dx) > 5) d.moved = true;
    if (d.moved) el.scrollLeft = d.startLeft - dx;
  }
  function categoryUp() {
    categoryDrag.current.active = false;
  }
  function categoryClickCapture(e: React.MouseEvent) {
    if (categoryDrag.current.moved) {
      e.preventDefault();
      e.stopPropagation();
      categoryDrag.current.moved = false;
    }
  }

  function sidebarNavDown(e: React.PointerEvent<HTMLElement>) {
    const el = sidebarNavRef.current;
    if (!el) return;
    sidebarNavDrag.current = { active: true, startX: e.clientX, startLeft: el.scrollLeft, moved: false };
  }
  function sidebarNavMove(e: React.PointerEvent<HTMLElement>) {
    const el = sidebarNavRef.current;
    const d = sidebarNavDrag.current;
    if (!el || !d.active) return;
    const dx = e.clientX - d.startX;
    if (Math.abs(dx) > 5) d.moved = true;
    if (d.moved) el.scrollLeft = d.startLeft - dx;
  }
  function sidebarNavUp() {
    sidebarNavDrag.current.active = false;
  }
  function sidebarNavClickCapture(e: React.MouseEvent) {
    if (sidebarNavDrag.current.moved) {
      e.preventDefault();
      e.stopPropagation();
      sidebarNavDrag.current.moved = false;
    }
  }
  useEffect(() => {
    if (!searchRequest || view !== "market") return;
    marketRef.current?.scrollIntoView({ block: "start" });
    marketRef.current?.focus({ preventScroll: true });
  }, [searchRequest, view]);
  useEffect(() => {
    if (!smartMode || !smartQuery.trim() || view !== "market") return;
    let alive = true;
    setSmartBusy(true);
    setSmartError("");
    setSmartResult(null);
    api<SmartSearchResult>("/items/smart-search", "POST", {
      query: smartQuery,
      page: smartPage,
      size: 12,
      sort,
    })
      .then((d) => {
        if (alive) setSmartResult(d);
      })
      .catch((e) => {
        if (alive) setSmartError(e.message);
      })
      .finally(() => {
        if (alive) setSmartBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [smartQuery, smartPage, sort, smartMode, view, smartRequest]);
  useEffect(() => {
    const target = reporting ? reportRef.current : null;
    target?.scrollIntoView({ block: "center" });
    target?.focus({ preventScroll: true });
  }, [reporting]);
  useEffect(() => {
    if (!avatarMenu) return;
    const onDown = (event: MouseEvent) => {
      if (!avatarMenuRef.current?.contains(event.target as Node)) {
        setAvatarMenu(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [avatarMenu]);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    const listener = () => {
      setView(currentView());
      setPendingConversation(currentConversation());
      setPage(1);
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    if (toast) {
      const t = window.setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    Promise.all([api<Meta>("/meta"), api<{ user: User | null }>("/auth/me")])
      .then(([m, u]) => {
        setMeta(m);
        setUser(u.user);
      })
      .catch((e) => setFatal(e.message));
  }, []);
  useEffect(() => {
    if (revision)
      api<Meta>("/meta")
        .then(setMeta)
        .catch(() => {});
  }, [revision]);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("item");
    if (id)
      api<Item>("/items/" + encodeURIComponent(id))
        .then((i) => {
          setSelected(i);
          setModal("detail");
        })
        .catch((e) => setToast(e.message));
  }, []);

  // 页面与商品停留时长埋点上报 (Page & Item Dwell Time via sendBeacon)
  useEffect(() => {
    const activePage =
      modal === "detail" && selected
        ? "item_detail"
        : modal === "publish"
        ? "publish"
        : modal === "wanted"
        ? "post_wanted"
        : view;
    const activeItemId = modal === "detail" && selected ? selected.id : null;
    let enterTime = Date.now();

    const reportDwell = () => {
      const durationSeconds = Math.round((Date.now() - enterTime) / 1000);
      if (durationSeconds < 2) return;
      const payload = JSON.stringify({
        page: activePage,
        item_id: activeItemId,
        duration_seconds: Math.min(durationSeconds, 7200),
      });

      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: "application/json" });
        navigator.sendBeacon("/api/v1/analytics/dwell", blob);
      } else {
        fetch("/api/v1/analytics/dwell", {
          method: "POST",
          body: payload,
          headers: { "Content-Type": "application/json" },
          keepalive: true,
        }).catch(() => {});
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        reportDwell();
      } else {
        enterTime = Date.now();
      }
    };

    window.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("pagehide", reportDwell);
    return () => {
      window.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("pagehide", reportDwell);
      reportDwell();
    };
  }, [view, modal, selected?.id]);
  const navigate = (v: View) => {
    location.hash = v;
    setPendingConversation(null);
    setView(v);
    setPage(1);
    setOnSale(v === "market");
    if (v === "wanted") {
      setSmartMode(false);
      setSmartQuery("");
      setSmartResult(null);
    }
  };
  const needUser = () => {
    if (!user) {
      setModal("login");
      return false;
    }
    return true;
  };
  function signedIn(account: User) {
    setSessionExpired(false);
    setSessionEpoch((n) => n + 1);
    setUser(account);
    setCompare([]);
    if (feedbackAfterLogin.current) {
      feedbackAfterLogin.current = false;
      setModal("feedback");
      refresh();
      return;
    }
    const conversationId = currentConversation();
    setPendingConversation(conversationId);
    if (conversationId) {
      setModal(null);
      setChatItem(null);
      setChatDraft("");
    } else if (selected) {
      void api<Item>(`/items/${selected.id}`).then((item) => {
        setSelected(item);
        setModal("detail");
      }).catch((error) => { setModal(null); setToast((error as Error).message); });
    } else setModal(null);
    refresh();
  }
  async function operate(task: () => Promise<unknown>, message?: string) {
    setBusy(true);
    try {
      await task();
      refresh();
      if (message) setToast(message);
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function openForm(type: "intent" | "publish" | "wanted", text = "") {
    if (!needUser()) return;
    if (type === "intent") { setIntentQuery(text); setEditingIntent(null); }
    if (type === "wanted") { setEditingWanted(null); setPublishingIntent(null); }
    if (type === "publish") {
      setPrefill(null);
      setEditingItem(null);
      setCopiedDraft(null);
    }
    setModal(type);
  }
  async function openItem(item: Pick<Item, "id">, fromChat = false) {
    setReporting(false);
    setReportText("");
    setSimilar([]);
    try {
      const fresh = await api<Item>("/items/" + item.id);
      setDetailFromChat(fromChat);
      setSelected(fresh);
      setModal("detail");
      return true;
    } catch (e) {
      setToast((e as Error).message);
      return false;
    }
  }
  function favorite(item: Item) {
    if (!needUser()) return;
    void operate(
      async () => {
        await api(
          "/items/" + item.id + "/favorite",
          item.is_favorite ? "DELETE" : "POST",
        );
        if (selected?.id === item.id)
          setSelected({ ...item, is_favorite: !item.is_favorite });
      },
      item.is_favorite ? "已取消收藏" : "已收藏，喜欢的好物不再错过",
    );
  }
  function addCompare(item: Item) {
    if (compare.some((i) => i.id === item.id))
      setCompare(compare.filter((i) => i.id !== item.id));
    else if (compare.length < 3) setCompare([...compare, item]);
    else setToast("每次最多对比 3 件商品");
  }
  function removeCompare(id: string) {
    setCompare((current) => current.filter((item) => item.id !== id));
    if (modal === "compare" && compare.length <= 2) setModal(null);
  }
  async function copy(text: string, message: string) {
    try {
      await navigator.clipboard.writeText(text);
      setToast(message);
    } catch {
      setToast("复制失败，请手动选中文字复制");
    }
  }
  function searchSubmit(e: FormEvent) {
    e.preventDefault();
    const nextQuery = search.trim().replace(/\s+/g, " ");
    setSearch(nextQuery);
    setQuery(nextQuery);
    if (view !== "wanted" && smartMode && nextQuery) {
      setSmartQuery(nextQuery);
      setSmartPage(1);
      setSmartResult(null);
      setSmartError("");
    } else {
      setSmartQuery("");
      setSmartResult(null);
      setPage(1);
    }
    navigate(view === "wanted" ? "wanted" : "market");
    setSearchRequest((value) => value + 1);
  }
  function clearSearch() {
    setSearch("");
    setQuery("");
    setSmartQuery("");
    setSmartResult(null);
    setSmartError("");
    setPage(1);
    setSmartPage(1);
  }
  const searchBarProps = {
    target: view === "wanted" ? "wanted" as const : "market" as const,
    value: search,
    showClear: Boolean(search || query || (view !== "wanted" && smartQuery)),
    smartMode,
    onChange: setSearch,
    onSubmit: searchSubmit,
    onClear: clearSearch,
    onToggleSmart: () => {
      setSmartMode(!smartMode);
      if (smartMode) {
        setSmartQuery("");
        setSmartResult(null);
      }
    },
  };
  const listParams = new URLSearchParams({
    q: query,
    category,
    campus,
    sort,
    page: String(page),
    size: "12",
  });
  if (price) listParams.set("max_price", price);
  if (view === "mine") listParams.set("mine", "true");
  if (view === "favorites") listParams.set("favorites", "true");
  if (!onSale) listParams.set("on_sale", "false");
  const listingView = ["market", "favorites", "mine"].includes(view);
  const items = useResource<{ items: Item[]; total: number }>(
    "/items/?" + listParams.toString(),
    revision,
    listingView && (view === "market" || !!user),
  );
  const intents = useResource<Intent[]>(
    "/intents/my",
    revision,
    view === "intents" && !!user,
    true,
  );
  const wanted = useResource<Wanted[]>(
    "/wanted/?" + new URLSearchParams({ q: query }).toString(),
    revision,
    view === "wanted",
  );
  const myWanted = useResource<Wanted[]>("/wanted/?mine=true", revision, view === "mywanted");
  const noticeRevision = revision + notificationRevision;
  const conversations = useResource<Conversation[]>("/conversations", noticeRevision, !!user, true, user?.id);
  const noticeResource = useResource<Notice[]>("/notifications/?unread_only=true", noticeRevision, !!user, true, user?.id);
  const notices = noticeResource.data ?? [];
  const summary = useResource<{ total: number; chat: number; pending_sale_feedback: number }>(
    "/notification-summary", noticeRevision, !!user, true, user?.id);
  const profileOverview = useResource<{ intents: number; listings: number; favorites: number; wanted: number }>(
    "/users/me/overview", revision, view === "profile" && !!user,
  );
  const taskNotices = useResource<Notice[]>(
    `/notifications/?intent_id=${encodeURIComponent(noticeIntent?.id ?? "")}`,
    noticeRevision,
    modal === "notifications" && !!noticeIntent && !!user,
    true,
    user?.id,
  );
  const saleFeedback = useResource<{ id: string; status: string; created_at: string }[]>(
    `/items/${selected?.id ?? ""}/sale-feedback`, revision,
    modal === "detail" && !!selected?.is_owner && !!selected?.sale_feedback_count,
  );
  const saleFeedbackMine = useResource<SaleFeedbackNotice[]>(
    "/sale-feedback/my", noticeRevision, !!user, true, user?.id,
  );
  const siteFeedbackNotices = useResource<FeedbackNotices>(
    "/feedback-notices", noticeRevision, !!user, true, user?.id,
  );
  useEffect(() => {
    if (modal !== "detail" || !selected?.id) { setSimilar([]); return; }
    let alive = true;
    void api<{ items: Item[] }>(`/items/${selected.id}/similar?limit=6`)
      .then((result) => { if (alive) setSimilar(result.items); })
      .catch(() => { if (alive) setSimilar([]); });
    return () => { alive = false; };
  }, [modal, selected?.id]);
  const openFeedback = (id: string | null = null) => { setFeedbackId(id); setModal("feedback"); };
  const visibleNotices = noticeIntent
    ? (taskNotices.data ?? []).filter((n) => n.intent_id === noticeIntent.id)
    : notices;
  const chatUnread = summary.data?.chat ?? 0;
  const feedbackPending = summary.data?.pending_sale_feedback ?? 0;
  const allUnread = summary.data?.total ?? 0;
  const personalView = ["profile", "intents", "messages", "favorites", "mine", "mywanted"].includes(view);
  const adminView = ["admin", "admin-chat", "admin-reports", "admin-logs", "admin-feedback", "admin-metrics"].includes(view);
  const adminSummary = useResource<AdminSummary>(
    "/admin/summary", revision, user?.role === "admin", true, user?.id,
  );

  if (!meta)
    return (
      <div className="boot">
        <Brand />
        {fatal ? (
          <>
            <p role="alert">暂时无法连接燕渡服务：{fatal}</p>
            <button
              className="button primary"
              onClick={() => location.reload()}
            >
              重新连接
            </button>
          </>
        ) : (
          <Busy>燕渡正在准备好物…</Busy>
        )}
      </div>
    );

  const renderNotice = (n: Notice) => (
    <article className={`notice ${n.is_read ? "" : "unread"}`} key={n.id}>
      <ProductArt item={n.item} />
      <div>
        <span className="task-status">
          {!n.available
            ? `${statusText[n.item.status] ?? "不在售"}，暂不可咨询`
            : n.verdict === "UNCERTAIN"
              ? "可能合适，部分条件待确认"
              : "有好物符合你的期待"}
        </span>
        <h3>{n.item.title}</h3>
        <p>{n.reason}</p>
        {n.evidence.length > 0 && (
          <details className="agent-evidence">
            <summary>
              查看
              {n.review_mode === "remote" ? "助手核对" : "关键词命中"}
              依据
            </summary>
            {n.evidence.map((e, index) => (
              <p key={index}>
                {e.criterion}：<q>{e.quote}</q>
              </p>
            ))}
          </details>
        )}
        {n.questions.length > 0 && (
          <div className="agent-questions">
            <strong>建议向卖家确认</strong>
            <ul>
              {n.questions.map((q, index) => (
                <li key={index}>{q}</li>
              ))}
            </ul>
            <span className="hint">这些问题会加入咨询草稿。</span>
          </div>
        )}
        <div>
          <button
            className="text-button"
            onClick={() => {
              void operate(() =>
                api(`/notifications/${n.id}/read`, "PATCH"),
              );
              void openItem(n.item);
            }}
          >
            查看商品
            <ArrowRight size={14} />
          </button>
          {noticeIntent && noticeIntent.status !== "COMPLETED" && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                void operate(
                  async () => {
                    await api(`/intents/${noticeIntent.id}/complete`, "POST", {
                      item_id: n.item.id,
                    });
                    setModal(null);
                  },
                  "已记录买到这件商品，代蹲已结束",
                )
              }
            >
              已买到这件
            </button>
          )}
          {!n.is_read && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                void operate(() =>
                  api(`/notifications/${n.id}/read`, "PATCH"),
                )
              }
            >
              标为已读
            </button>
          )}
        </div>
      </div>
    </article>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand-button"
          onClick={() => navigate("market")}
          aria-label="燕渡首页"
        >
          <Brand />
        </button>
        <p className="brand-caption">旧物渡新主，学海渡轻舟</p>
        <nav
          aria-label="主导航"
          ref={sidebarNavRef}
          onPointerDown={sidebarNavDown}
          onPointerMove={sidebarNavMove}
          onPointerUp={sidebarNavUp}
          onPointerCancel={sidebarNavUp}
          onClickCapture={sidebarNavClickCapture}
        >
          {nav.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={`nav-item ${view === key || (key === "profile" && personalView) ? "active" : ""}`}
              onClick={() => {
                setCategory("");
                setPrice("");
                navigate(key as View);
              }}
            >
              <Icon size={20} strokeWidth={1.7} />
              <span>{label}</span>
              {key === "profile" && chatUnread > 0 && <span className="nav-new">{chatUnread}</span>}
            </button>
          ))}
          {user?.role === "admin" && (
            <button
              className={`nav-item ${adminView ? "active" : ""}`}
              onClick={() => navigate("admin")}
            >
              <ShieldCheck size={20} />
              审核工作台
              {!!adminSummary.data?.pending_total && <span className="nav-new">{adminSummary.data.pending_total}</span>}
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="contact-actions">
          <button
            className="sidebar-contact"
            onClick={() => void copy("pkuyandu@163.com", "邮箱已复制")}
          >
            <Mail size={15} />
            <span>
              <strong>联系我们</strong>
            </span>
          </button>
          <button type="button" className="sidebar-contact" onClick={() => openFeedback()}>
            <MessageCircle size={15} /><span><strong>意见反馈</strong></span>
          </button>
          </div>
          <small className="contact-email">pkuyandu@163.com</small>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="mobile-brand">
            <Brand small />
          </div>
          <SearchBar {...searchBarProps} />
          <div className="top-actions">
            <button className="icon-button theme-toggle" type="button"
              aria-label={theme === "dark" ? "切换到日间模式" : "切换到夜间模式"}
              title={theme === "dark" ? "日间模式" : "夜间模式"}
              aria-pressed={theme === "dark"}
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
              {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            <label className="campus-picker">
              <MapPin size={16} />
              <select
                aria-label="选择校区"
                value={campus}
                onChange={(e) => {
                  setCampus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">全部校区</option>
                {meta.campuses
                  .filter((c) => c !== "不限校区")
                  .map((c) => (
                    <option key={c}>{c}</option>
                  ))}
              </select>
            </label>
            <button
              className="notification-button icon-button"
              aria-label={`通知${allUnread ? `，${allUnread} 条未读` : ""}`}
              onClick={() => {
                setNoticeIntent(null);
                setModal("notifications");
              }}
            >
              <Bell size={21} />
              {allUnread > 0 && <span>{allUnread}</span>}
            </button>
            <div className="avatar-menu-wrap" ref={avatarMenuRef}>
              <button
                className="avatar-button"
                onClick={() => user ? setAvatarMenu(!avatarMenu) : setModal("login")}
                aria-label={user ? `查看${user.nickname}的个人主页${chatUnread ? `，${chatUnread} 条未读消息` : ""}` : "登录或注册"}
                aria-haspopup={user ? "menu" : undefined}
                aria-expanded={user ? avatarMenu : undefined}
              >
                <span className={`avatar avatar-color-${user?.avatar_color ?? "sage"}`}>{user ? user.nickname[0] : "访"}</span>
                <span className="avatar-name">{user?.nickname || "登录/注册"}</span>
                {user && chatUnread > 0 && <span className="avatar-unread" aria-hidden="true" />}
              </button>
              {user && avatarMenu && (
                <div className="avatar-menu" role="menu">
                  <button
                    role="menuitem"
                    className="avatar-menu-item"
                    onClick={() => { setAvatarMenu(false); navigate("profile"); }}
                  >
                    查看个人主页
                  </button>
                  <button
                    role="menuitem"
                    className="avatar-menu-item"
                    onClick={() => { setAvatarMenu(false); setEditProfile(true); navigate("profile"); }}
                  >
                    编辑资料
                  </button>
                  <button
                    role="menuitem"
                    className="avatar-menu-item"
                    onClick={() => { setAvatarMenu(false); setModal("login"); }}
                  >
                    账号设置
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main>
          {personalView && user && <ProfileNav view={view as PersonalView} onNavigate={navigate} unread={chatUnread} />}
          {adminView && user && <AdminNav view={view as AdminView} onNavigate={navigate} counts={adminSummary.data} />}
          {view === "profile" && (user ? <ProfileHome
            user={user} meta={meta} overview={profileOverview.data}
            unread={chatUnread} conversations={conversations.data?.length ?? 0}
            onNavigate={navigate} onAccount={() => setModal("login")}
            onUpdated={(account) => { setUser(account); setToast("个人资料已更新"); refresh(); }}
            onError={setToast}
            autoEdit={editProfile}
            onAutoEditConsumed={() => setEditProfile(false)}
          /> : <Empty title="登录后查看个人主页" text="使用北大邮箱登录，集中管理你的代蹲、消息、收藏与发布。"
            action="登录或注册" onAction={() => setModal("login")} />)}
          {(view === "market" || view === "wanted") && <SearchBar {...searchBarProps} mobile />}
          {view === "market" && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <span className="eyebrow">
                    <span className="live-dot" /> GOOD THINGS, NEXT CHAPTER
                  </span>
                  <h1>
                    旧物有新处，
                    <br />
                    好物等你来<span>。</span>
                  </h1>
                  <p>
                    从一本翻过的书，到陪你熬夜的台灯。
                    <br />
                    你的刚好闲置，也许是同学的正好需要。
                  </p>
                  <button
                    className="button primary"
                    onClick={() => openForm("publish")}
                  >
                    <Plus size={18} />
                    发布我的闲置
                    <ArrowRight size={16} />
                  </button>
                  <div className="hero-foot">
                    <Leaf size={15} />
                    <span>让闲置流转，让校园更有温度</span>
                  </div>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="hero-orbit orbit-one" />
                  <div className="hero-orbit orbit-two" />
                  <svg viewBox="0 0 420 320">
                    <ellipse
                      cx="233"
                      cy="261"
                      rx="111"
                      ry="11"
                      fill="#b5c4a2"
                      opacity=".23"
                    />
                    <path d="m130 167 191-54-79 121z" fill="#ecddbe" />
                    <path
                      d="m130 167 89 14 102-68-79 121-23-53"
                      fill="#faf6e8"
                    />
                    <path d="m219 181 7 36 16 17" fill="#d4c7a8" />
                    <path
                      d="m106 107 19-5-8 17"
                      fill="none"
                      stroke="#62826b"
                      strokeWidth="2"
                    />
                    <path
                      d="M292 84q27 2 34-21m-10 13 9-4"
                      stroke="#81966b"
                      fill="none"
                    />
                    <path
                      d="M302 231q6-57 27-89m-18 62q29-4 35-26-23 1-35 26m10-33q-21-9-19-30 23 8 19 30m-16 48q-25-1-31-22 29-1 31 22"
                      stroke="#78926a"
                      strokeWidth="2"
                      fill="#a7b790"
                    />
                    <circle cx="129" cy="217" r="4" fill="#e1b871" />
                    <circle cx="272" cy="58" r="3" fill="#81976e" />
                    <path
                      d="m93 161 8-9m-10 0 10 9"
                      stroke="#afbc97"
                      strokeWidth="2"
                    />
                  </svg>
                  <span className="floating-note note-one">
                    <BookOpen size={17} />
                    知识，也可以接力
                  </span>
                  <span className="floating-note note-two">
                    <Check size={15} />
                    在校园，遇见刚刚好
                  </span>
                  <span className="handwritten">
                    a little less waste,
                    <br />a little more connection.
                  </span>
                </div>
              </section>
              <section className="intent-banner">
                <div className="intent-symbol">
                  <Sparkles size={25} />
                </div>
                <div className="intent-banner-text">
                  <h2>你许个愿，燕渡帮你找。</h2>
                  <p>不用反复刷，有合适的好物就通知你。</p>
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    openForm("intent", intentQuery);
                  }}
                >
                  <input
                    aria-label="一句话描述需求"
                    value={intentQuery}
                    onChange={(e) => setIntentQuery(e.target.value)}
                    placeholder="试试：300 元以内的静音鼠标"
                  />
                  <button className="button dark" type="submit">
                    帮我代蹲
                    <ArrowRight size={16} />
                  </button>
                </form>
              </section>
            </>
          )}
          {listingView && (
            <section
              className="market-section"
              ref={marketRef}
              tabIndex={-1}
              aria-label="商品搜索结果"
            >
              {view === "market" ? (
                <div className="section-heading">
                  <div>
                    <h2>
                      {smartMode && smartQuery
                        ? "智能搜索"
                        : "发现校园好物"}{" "}
                      <span className="small-dot" />
                    </h2>
                    <p>
                      {smartMode && smartQuery
                        ? "说人话，也能搜得懂。"
                        : "值得拥有的，不一定是全新的。"}
                    </p>
                  </div>
                  <span className="listing-count">
                    {smartMode && smartQuery
                      ? `${smartResult?.total ?? "…"} 件结果`
                      : `${items.data?.total ?? "…"} 件好物 · 等待新主人`}
                  </span>
                </div>
              ) : (
                <Intro
                  kicker={
                    view === "favorites"
                      ? "YOUR LITTLE COLLECTION"
                      : "PASS IT FORWARD"
                  }
                  title={
                    view === "favorites"
                      ? "心动好物，留在这里。"
                      : "我发布的闲置"
                  }
                  text={
                    view === "favorites"
                      ? "遇到喜欢的先收藏，慢慢找到合适的那一件。"
                      : "管理商品状态，让闲置顺利开启下一段故事。"
                  }
                >
                  {view === "mine" && (
                    <button
                      className="button primary"
                      onClick={() => openForm("publish")}
                    >
                      <Plus size={17} />
                      发布闲置
                    </button>
                  )}
                </Intro>
              )}
              {smartMode && smartQuery ? (
                <div className="smart-search-results">
                  <div className="smart-understanding">
                    <div className="smart-understanding-head">
                      <Sparkles size={17} />
                      <span>已理解你的意思</span>
                      <button
                        className="query-tag"
                        onClick={() => {
                          setSmartQuery("");
                          setSmartResult(null);
                          setSmartMode(false);
                        }}
                      >
                        “{smartQuery}”<X size={13} />
                      </button>
                    </div>
                    {smartBusy ? (
                      <p className="muted">正在理解并搜索…</p>
                    ) : smartResult ? (
                      <>
                        <div className="pills smart-pills">
                          {smartResult.parsed.category && (
                            <span>分类：{smartResult.parsed.category}</span>
                          )}
                          {smartResult.parsed.max_price !== null && (
                            <span>
                              {smartResult.parsed.around_price
                                ? "预算约"
                                : "预算"}
                              ：¥{money(smartResult.parsed.max_price)}
                              {smartResult.parsed.around_price ? "左右" : "以内"}
                            </span>
                          )}
                          {smartResult.parsed.campus &&
                            smartResult.parsed.campus !== "不限校区" && (
                              <span>校区：{smartResult.parsed.campus}</span>
                            )}
                          {smartResult.parsed.condition_grade && (
                            <span>
                              成色：{smartResult.parsed.condition_grade}以上
                            </span>
                          )}
                          {smartResult.parsed.keywords.map((k) => (
                            <span key={k}>{k}</span>
                          ))}
                          {smartResult.parsed.excluded_keywords.map((k) => (
                            <span key={k} className="excluded">
                              不要：{k}
                            </span>
                          ))}
                          {smartResult.parsed.preferences.map((k) => (
                            <span key={k} className="preference">
                              偏好：{k}
                            </span>
                          ))}
                        </div>
                        {smartResult.parsed.clarification && (
                          <p className="smart-clarification">
                            {smartResult.parsed.clarification}
                          </p>
                        )}
                      </>
                    ) : null}
                  </div>
                  <div className="smart-results-toolbar">
                    <span className="listing-count">
                      {smartResult?.total ?? "…"} 件好物
                    </span>
                    <label className="sort-picker smart-sort">
                      <ArrowDownUp size={14} />
                      <select
                        aria-label="智能搜索结果排序"
                        value={sort}
                        onChange={(e) => {
                          setSort(e.target.value);
                          setSmartPage(1);
                        }}
                      >
                        <option value="recommended">最相关</option>
                        <option value="newest">最新发布</option>
                        <option value="price_asc">价格从低到高</option>
                        <option value="price_desc">价格从高到低</option>
                      </select>
                    </label>
                  </div>
                  {smartError ? (
                    <Empty
                      title="智能搜索暂时不可用"
                      text={smartError}
                      action="重试"
                      onAction={() => setSmartRequest((v) => v + 1)}
                    />
                  ) : !smartBusy && smartResult && smartResult.items.length ? (
                    <>
                      <div className="item-grid">
                        {smartResult.items.map((item) => (
                          <Card
                            key={item.id}
                            item={item}
                            onOpen={openItem}
                            onFavorite={favorite}
                            onCompare={addCompare}
                            selected={compare.some((i) => i.id === item.id)}
                          />
                        ))}
                      </div>
                      {smartResult.total > 12 && (
                        <div className="pagination">
                          <button
                            className="button secondary"
                            disabled={smartResult.page <= 1}
                            onClick={() => setSmartPage(smartResult.page - 1)}
                          >
                            <ChevronLeft size={16} />
                            上一页
                          </button>
                          <span>
                            {smartResult.page} /{" "}
                            {Math.ceil(smartResult.total / 12)}
                          </span>
                          <button
                            className="button secondary"
                            disabled={smartResult.page * 12 >= smartResult.total}
                            onClick={() => setSmartPage(smartResult.page + 1)}
                          >
                            下一页
                            <ChevronRight size={16} />
                          </button>
                        </div>
                      )}
                    </>
                  ) : !smartBusy && smartResult ? (
                    <Empty
                      title="没有找到特别贴合的"
                      text="换个说法试试，或开启代蹲，让新上架的商品自动匹配你。"
                      action="发布求购"
                      onAction={() => openForm("wanted")}
                    />
                  ) : null}
                </div>
              ) : (
                <>
                <div
                  className="category-tabs"
                  role="group"
                  aria-label="物品分类"
                  ref={categoryTabsRef}
                  onPointerDown={categoryDown}
                  onPointerMove={categoryMove}
                  onPointerUp={categoryUp}
                  onPointerCancel={categoryUp}
                  onClickCapture={categoryClickCapture}
                >
                {["全部好物", ...meta.categories].map((c, index) => {
                  const Icon = [
                    LayoutGrid,
                    BookOpen,
                    Monitor,
                    Bike,
                    Lamp,
                    Shirt,
                    Users,
                  ][index];
                  return (
                    <button
                      key={c}
                      className={category === (index ? c : "") ? "active" : ""}
                      onClick={() => {
                        setCategory(index ? c : "");
                        setPage(1);
                      }}
                    >
                      <Icon size={17} />
                      {index
                        ? [
                            "课程书籍",
                            "数码影音",
                            "出行运动",
                            "宿舍生活",
                            "服饰周边",
                            "人员招募",
                          ][index - 1]
                        : c}
                    </button>
                  );
                })}
              </div>
              <div className="filter-row">
                <div className="filter-left">
                  <span className="filter-label">筛选</span>
                  <label>
                    <span className="sr-only">最高价格</span>
                    <select
                      value={price}
                      onChange={(e) => {
                        setPrice(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">不限价格</option>
                      <option value="50">50 元以内</option>
                      <option value="100">100 元以内</option>
                      <option value="300">300 元以内</option>
                      <option value="500">500 元以内</option>
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">售卖状态</span>
                    <select
                      value={onSale ? "on_sale" : "all"}
                      onChange={(e) => {
                        setOnSale(e.target.value === "on_sale");
                        setPage(1);
                      }}
                    >
                      <option value="on_sale">只看在售</option>
                      <option value="all">所有好物</option>
                    </select>
                  </label>
                  {query && (
                    <button
                      className="query-tag"
                      onClick={clearSearch}
                    >
                      “{query}”<X size={13} />
                    </button>
                  )}
                </div>
                <label className="sort-picker">
                  <ArrowDownUp size={14} />
                  <select
                    aria-label="商品排序"
                    value={sort}
                    onChange={(e) => {
                      setSort(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="recommended">为你挑选</option>
                    <option value="newest">最新发布</option>
                    <option value="price_asc">价格从低到高</option>
                    <option value="price_desc">价格从高到低</option>
                  </select>
                </label>
              </div>
              {query && <p className="search-rule">多个关键词用空格分隔，结果需同时包含所有关键词。</p>}
              {!user && view !== "market" ? (
                <Empty
                  title="登录后，继续你的校园之旅"
                  text="收藏和发布记录会跟随你的账号保存。"
                  action={meta.demo_mode ? "进入演示账号" : "登录或注册"}
                  onAction={() => setModal("login")}
                />
              ) : items.loading ? (
                <Busy />
              ) : items.error ? (
                <Empty
                  title="好物暂时没有加载出来"
                  text={items.error}
                  action="重试"
                  onAction={refresh}
                />
              ) : items.data?.items.length ? (
                <>
                  <div className="item-grid">
                    {items.data.items.map((item) => (
                      <Card
                        key={item.id}
                        item={item}
                        onOpen={openItem}
                        onFavorite={favorite}
                        onCompare={addCompare}
                        selected={compare.some((i) => i.id === item.id)}
                      />
                    ))}
                  </div>
                  {items.data.total > 12 && (
                    <div className="pagination">
                      <button
                        className="button secondary"
                        disabled={page <= 1}
                        onClick={() => setPage(page - 1)}
                      >
                        <ChevronLeft size={16} />
                        上一页
                      </button>
                      <span>
                        {page} / {Math.ceil(items.data.total / 12)}
                      </span>
                      <button
                        className="button secondary"
                        disabled={page * 12 >= items.data.total}
                        onClick={() => setPage(page + 1)}
                      >
                        下一页
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <Empty
                  title={
                    query ? "没有找到匹配的好物" : view === "favorites"
                      ? "把喜欢的好物，先收藏起来"
                      : view === "mine"
                        ? "你的第一件闲置，还在等待出发"
                        : "暂时没有合适的好物"
                  }
                  text={
                    query ? "换个关键词试试，或清空搜索查看好物。" : view === "market"
                      ? "换个筛选条件，或留下求购，让有闲置的同学找到你。"
                      : "每一件物品，都值得一段新的故事。"
                  }
                  action={
                    query ? "清空搜索" : view === "market"
                      ? "发布求购"
                      : view === "mine"
                        ? "发布闲置"
                        : "去逛逛校园"
                  }
                  onAction={() =>
                    query ? clearSearch() : view === "market"
                      ? openForm("wanted")
                      : view === "mine"
                        ? openForm("publish")
                        : navigate("market")
                  }
                />
              )}
                </>
              )}
            </section>
          )}
          {view === "intents" && (
            <>
              <Intro
                kicker="LET YANDU KEEP AN EYE OUT"
                title="你忙你的，燕渡帮你找。"
                text="每一个小小心愿，都值得被认真留意。"
              >
                <button
                  className="button primary"
                  onClick={() => openForm("intent")}
                >
                  <Plus size={17} />
                  新建代蹲
                </button>
              </Intro>
              <div className="info-strip">
                <Sparkles size={17} />
                <span>
                  {meta.ai_mode === "local"
                    ? "当前为本地关键词匹配演示"
                    : "买家助手已开启：理解需求并核对商品描述"}{" "}
                  · 持续留意，可随时暂停或结束
                </span>
              </div>
              {!user ? (
                <Empty
                  title="登录后，让燕渡替你留意"
                  text="你的需求和命中记录会保存在账号中。"
                  action={meta.demo_mode ? "进入演示账号" : "登录或注册"}
                  onAction={() => setModal("login")}
                />
              ) : intents.loading ? (
                <Busy />
              ) : intents.error ? (
                <Empty
                  title="任务暂时无法加载"
                  text={intents.error}
                  action="重试"
                  onAction={refresh}
                />
              ) : !intents.data?.length ? (
                <Empty
                  title="留一个心愿给燕渡"
                  text="例如：万柳附近 300 元以内的静音鼠标。现在没有也没关系，新商品上架后会再匹配。"
                  action="创建第一个代蹲任务"
                  onAction={() => openForm("intent")}
                />
              ) : (
                <div className="intent-list">
                  {intents.data.map((i) => (
                    <article className="intent-card" key={i.id}>
                      <div className="intent-card-top">
                        <span
                          className={`task-status ${i.status === "ACTIVE" ? "active" : ""}`}
                        >
                          <span className="live-dot" />
                          {i.status === "ACTIVE"
                            ? "正在替你留意"
                            : statusText[i.status]}
                        </span>
                        <span>{i.wanted_id ? "已关联求购看板" : "私密代蹲"}</span>
                      </div>
                      <h3>{i.raw_query}</h3>
                      <div className="pills">
                        <span>{i.category || "不限分类"}</span>
                        <span>
                          {i.max_price === null
                            ? "不限预算"
                            : `¥${money(i.max_price)} 以内`}
                        </span>
                        <span>{i.campus}</span>
                        {i.keywords.map((k) => (
                          <span key={k}>{k}</span>
                        ))}
                      </div>
                      {(i.excluded_keywords.length > 0 ||
                        i.preferences.length > 0) && (
                        <div className="agent-conditions">
                          {i.excluded_keywords.length > 0 && (
                            <p>不接受：{i.excluded_keywords.join("、")}</p>
                          )}
                          {i.preferences.length > 0 && (
                            <p>可选偏好：{i.preferences.join("、")}</p>
                          )}
                        </div>
                      )}
                      {i.status === "ACTIVE" && i.matching_state !== "DONE" && (
                        <p className="hint" role="status">
                          {i.matching_state === "FAILED"
                            ? "商品核对暂时失败，你的代蹲条件已保存。"
                            : "助手正在核对候选商品，完成后会更新通知。"}
                          {i.matching_state === "FAILED" && (
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() =>
                                void operate(
                                  () => api(`/intents/${i.id}/retry`, "POST"),
                                  "已重新安排商品核对",
                                )
                              }
                            >
                              重新核对
                            </button>
                          )}
                        </p>
                      )}
                      <div className="intent-card-bottom">
                        <button
                          className="text-button"
                          onClick={() => {
                            setNoticeIntent(i);
                            setModal("notifications");
                          }}
                        >
                          <Bell size={16} />
                          累计发现 {i.match_count} 件好物
                          <ArrowRight size={14} />
                        </button>
                        {i.status !== "COMPLETED" && (
                          <div className="task-actions">
                            <button disabled={busy} onClick={() => void operate(
                              () => api(`/intents/${i.id}/complete`, "POST", {}), "已记录买到商品，代蹲已结束")}>已买到</button>
                            <button
                              disabled={busy}
                              onClick={() =>
                                void operate(() =>
                                  api(`/intents/${i.id}`, "PATCH", {
                                    action:
                                      i.status === "ACTIVE"
                                        ? "pause"
                                        : "resume",
                                  }),
                                )
                              }
                            >
                              {i.status === "ACTIVE" ? (
                                <Pause size={14} />
                              ) : (
                                <Play size={14} />
                              )}{" "}
                              {i.status === "ACTIVE" ? "暂停" : "继续"}
                            </button>
                            <button disabled={busy} onClick={() => { setEditingIntent(i); setModal("intent"); }}>编辑条件</button>
                            <button disabled={busy} onClick={() => {
                              if (i.wanted_id) navigate("mywanted");
                              else { setPublishingIntent(i); setEditingWanted(null); setModal("wanted"); }
                            }}>{i.wanted_id ? "查看求购" : "发布到求购看板"}</button>
                            <button
                              disabled={busy}
                              onClick={() =>
                                void operate(
                                  () => api(`/intents/${i.id}`, "DELETE"),
                                  "代蹲已结束",
                                )
                              }
                            >
                              结束
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
          {view === "wanted" && (
            <>
              <Intro
                kicker="SOMEONE MIGHT HAVE WHAT YOU NEED"
                title="你需要的，也许恰好有人闲置。"
                text="在这里写下需要，让好物与好物的下一位主人相遇。"
              >
                <button
                  className="button primary"
                  onClick={() => openForm("wanted")}
                >
                  <Plus size={17} />
                  发布求购
                </button>
              </Intro>
              <p className="search-rule">多个关键词用空格分隔，结果需同时包含所有关键词。</p>
              {query && !wanted.loading && !wanted.error && (
                <p className="wanted-search-summary" role="status">
                  “{query}”的搜索结果：显示 {wanted.data?.length ?? 0} 条求购
                </p>
              )}
              {wanted.loading ? (
                <Busy />
              ) : wanted.error ? (
                <Empty
                  title="求购暂时无法加载"
                  text={wanted.error}
                  action="重试"
                  onAction={refresh}
                />
              ) : wanted.data?.length ? (
                <div className="wanted-grid">
                  {wanted.data.map((w) => (
                    <article className="wanted-card" key={w.id}>
                      <div className="wanted-card-top">
                        <span className="category-label">{w.category || "不限分类"}</span>
                        <Sprout size={21} />
                      </div>
                      <h3>{w.title}</h3>
                      <p>{w.description}</p>
                      <div className="wanted-budget">
                        预算 <strong>{w.budget == null ? "不限预算" : `¥${money(w.budget)}`}</strong>
                        <span>
                          <MapPin size={13} />
                          {campusShort(w.campus)}
                        </span>
                      </div>
                      <div className="wanted-bottom">
                        <span>
                          <span className="mini-avatar">
                            {w.buyer.nickname[0]}
                          </span>
                          {w.buyer.nickname}
                        </span>
                        {w.is_owner ? (
                          <div className="wanted-actions">
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => {
                                setEditingWanted(w);
                                setPublishingIntent(null);
                                setModal("wanted");
                              }}
                            >
                              编辑
                            </button>
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => void operate(() => api(`/wanted/${w.id}`, "DELETE"), "求购与代蹲已一起结束")}
                            >
                              我已找到
                              <Check size={15} />
                            </button>
                          </div>
                        ) : (
                          <button
                            className="text-button"
                            onClick={() => {
                              if (needUser()) {
                                setPrefill(w);
                                setModal("publish");
                              }
                            }}
                          >
                            我有这件物品
                            <ArrowRight size={15} />
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  title={query ? "没有找到匹配的求购" : "第一个心愿，由你开始"}
                  text={query ? "换个关键词试试，或清空搜索查看全部求购。" : "写下想找的物品，让同学们帮你留意。"}
                  action={query ? "清空搜索" : "发布求购"}
                  onAction={() => {
                    if (query) {
                      clearSearch();
                    } else {
                      openForm("wanted");
                    }
                  }}
                />
              )}
            </>
          )}
          {view === "mywanted" && (
            <>
              <Intro
                kicker="YOUR WISHES"
                title="我的求购"
                text="求购与代蹲共用需求和匹配记录，找到后可以一起结束。"
              >
                <button
                  className="button primary"
                  onClick={() => openForm("wanted")}
                >
                  <Plus size={17} />
                  发布求购
                </button>
              </Intro>
              {myWanted.loading ? (
                <Busy />
              ) : myWanted.error ? (
                <Empty
                  title="求购暂时无法加载"
                  text={myWanted.error}
                  action="重试"
                  onAction={refresh}
                />
              ) : myWanted.data?.length ? (
                <div className="wanted-grid">
                  {myWanted.data.map((w) => (
                    <article className="wanted-card" key={w.id}>
                      <div className="wanted-card-top">
                        <span className="category-label">{w.category || "不限分类"}</span>
                        <Sprout size={21} />
                      </div>
                      <h3>{w.title}</h3>
                      <p>{w.description}</p>
                      <div className="wanted-budget">
                        预算 <strong>{w.budget == null ? "不限预算" : `¥${money(w.budget)}`}</strong>
                        <span>
                          <MapPin size={13} />
                          {campusShort(w.campus)}
                        </span>
                      </div>
                      {w.intent ? <div className="wanted-matching">
                        <button className="text-button" onClick={() => { setNoticeIntent(w.intent); setModal("notifications"); }}>
                          <Bell size={15} />发现 {w.intent.match_count} 件好物 <ArrowRight size={14} />
                        </button>
                        <span>{w.status === "ACTIVE" ? w.intent.matching_state === "FAILED" ? "核对暂时失败，可在代蹲中重试" : w.intent.matching_state !== "DONE" ? "正在核对商品…" : "燕渡持续替你留意" : "求购与代蹲状态已同步"}</span>
                      </div> : w.status === "ACTIVE" && <button className="text-button" disabled={busy} onClick={() => void operate(() => api(`/wanted/${w.id}/watch`, "POST"), "已关联代蹲")}>开启代蹲</button>}
                      <div className="wanted-bottom">
                        <span>{w.status === "ACTIVE" ? w.intent ? "求购与代蹲进行中" : "求购中" : statusText[w.status] || "已结束"}</span>
                        <div className="wanted-actions">
                          {["ACTIVE", "PAUSED"].includes(w.status) ? <>
                            <button className="text-button" disabled={busy} onClick={() => { setEditingWanted(w); setPublishingIntent(null); setModal("wanted"); }}>编辑</button>
                            {w.intent && <button className="text-button" disabled={busy} onClick={() => void operate(() => api(`/intents/${w.intent!.id}`, "PATCH", { action: w.status === "ACTIVE" ? "pause" : "resume" }), w.status === "ACTIVE" ? "求购与代蹲已暂停" : "求购与代蹲已恢复")}>{w.status === "ACTIVE" ? "暂停" : "继续"}</button>}
                            <button className="text-button" disabled={busy} onClick={() => void operate(() => api(`/wanted/${w.id}`, "DELETE"), "求购与代蹲已一起结束")}>我已找到 <Check size={15} /></button>
                          </> : <button className="text-button" disabled={busy} onClick={() => void operate(() => api(`/wanted/${w.id}/renew`, "POST"), "求购与代蹲已重新开启")}>重新发布 <RefreshCw size={14} /></button>}
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  title="还没有发布求购"
                  text="写下想找的物品，让同学们帮你留意。"
                  action="发布求购"
                  onAction={() => openForm("wanted")}
                />
              )}
            </>
          )}
          {view === "messages" && (user ? (
            <ChatCenter key={user.id} user={user} conversations={conversations.data ?? []}
              initialItem={chatItem} initialDraft={chatDraft}
              initialConversationId={pendingConversation}
              onConversationOpened={consumeConversation}
              onOpenItem={(id) => void openItem({ id }, true)}
              onStarted={() => { setChatItem(null); setChatDraft(""); }} refresh={refresh} />
          ) : (
            <Empty title="登录后查看站内消息" text="通过北大邮箱验证后，就能和商品发布者沟通。"
              action="登录或注册" onAction={() => setModal("login")} />
          ))}
          {adminView && (
            <Admin
              user={user}
              revision={revision}
              refresh={refresh}
              notify={setToast}
              view={view as AdminView}
            />
          )}
          <footer>
            <Brand small />
            <span>校园生活的另一种循环</span>
            <div className="footer-contact-actions">
            <button
              className="footer-contact"
              onClick={() => void copy("pkuyandu@163.com", "邮箱已复制")}
            >
              联系我们
            </button>
            <button type="button" className="footer-contact" onClick={() => openFeedback()}>意见反馈</button>
            </div>
          </footer>
        </main>
      </div>
      {compare.length > 0 && (
        <div className="compare-tray">
          <div className="compare-tray-top">
            <span>
              <CheckCheck size={18} />
              已选 {compare.length} 件好物
            </span>
            <div className="compare-actions">
              <button
                className="button primary"
                disabled={compare.length < 2}
                onClick={() => setModal("compare")}
              >
                比较一下
                <ArrowRight size={15} />
              </button>
              <button
                className="icon-button"
                aria-label="清空对比"
                onClick={() => setCompare([])}
              >
                <X size={17} />
              </button>
            </div>
          </div>
          <div className="compare-selection">
            {compare.map((item) => (
              <button
                key={item.id}
                className="compare-chip"
                onClick={() => removeCompare(item.id)}
                aria-label={`移除对比：${item.title}`}
              >
                <span>{item.title}</span>
                <X size={14} />
              </button>
            ))}
          </div>
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <CircleHelp size={17} />
          {toast}
          <button aria-label="关闭提示" onClick={() => setToast("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {modal === "login" && (
        <Modal
          title={user ? "当前账号" : "欢迎来到燕渡"}
          onClose={() => { feedbackAfterLogin.current = false; setModal(null); }}
        >
          <div className="stack-form">
            {user?.email && <p className="auth-description">已验证邮箱：{user.email}<br />
              {user.has_password ? "已设置登录密码。重新验证邮箱可更换密码。" : "尚未设置登录密码。验证邮箱后即可设置。"}</p>}
            {!user && <AuthMethods meta={meta} onSignedIn={signedIn} />}
            {user?.email && <PasswordSetup meta={meta} initialEmail={user.email} onSignedIn={signedIn} />}
            {!user && meta.demo_mode && (
              <div className="demo-section"><p>或使用演示身份体验 <span>仅限本地演示</span></p><div className="login-options">
                {[
                  {
                    id: "buyer",
                    name: "林同学",
                    detail: "买家体验 · 许愿、收藏、接收匹配",
                  },
                  {
                    id: "seller",
                    name: "许同学",
                    detail: "卖家体验 · 发布、预订、标记售出",
                  },
                  {
                    id: "admin",
                    name: "管理员",
                    detail: "审核体验 · 检查举报、确认处理",
                  },
                ].map((p) => (
                  <button
                    disabled={busy}
                    key={p.id}
                    onClick={() =>
                      void operate(async () => {
                        const result = await api<{ user: User }>(
                          "/auth/demo",
                          "POST",
                          { profile: p.id },
                        );
                        signedIn(result.user);
                      }, `已进入${p.name}的演示账号`)
                    }
                  >
                    <span className="avatar">{p.name[0]}</span>
                    <span>
                      <strong>{p.name}</strong>
                      <small>{p.detail}</small>
                    </span>
                    <span className="demo-action">进入</span>
                  </button>
                ))}
              </div></div>
            )}
            {user && (
              <button
                className="button secondary full"
                disabled={busy}
                onClick={() =>
                  void operate(async () => {
                    await api("/auth/logout", "POST");
                    setUser(null);
                    setModal(null);
                    setCompare([]);
                    if (currentConversation()) setModal("login");
                    else navigate("market");
                  }, "已退出账号")
                }
              >
                <LogOut size={16} />
                退出登录
              </button>
            )}
          </div>
        </Modal>
      )}
      {modal === "intent" && (
        <Modal title={editingIntent ? "修改需求与代蹲条件" : "把需要的，交给燕渡留意"} onClose={() => { setModal(null); setEditingIntent(null); }}>
          <IntentForm
            meta={meta}
            initial={intentQuery}
            editingIntent={editingIntent}
            onDone={() => {
              setModal(null);
              setToast(editingIntent ? "需求已更新，关联求购已同步" : "需求已保存，燕渡会核对商品并持续代蹲");
              setEditingIntent(null);
              refresh();
              navigate("intents");
            }}
          />
        </Modal>
      )}
      {modal === "publish" && (
        <Modal
          title={editingItem ? "编辑发布的商品" : copiedDraft ? "再发一件：核对并发布" : "让闲置，开启下一段故事"}
          onClose={() => {
            setModal(null);
            setEditingItem(null);
            setCopiedDraft(null);
          }}
        >
          {(editingItem || prefill || copiedDraft ? <PublishForm key={editingItem?.id ?? copiedDraft?.id ?? prefill?.id} meta={meta} prefill={prefill} editingItem={editingItem} draft={copiedDraft}
            onDraftSaved={() => { setCopiedDraft(null); setModal(null); setToast("草稿已保存，可在发布中的待发布列表继续完善"); refresh(); }} onDone={() => {
              setModal(null);
              setEditingItem(null);
              setCopiedDraft(null);
              setToast(editingItem ? "商品信息已更新" : "好物发布成功，已为有需要的同学进行匹配");
              refresh();
              navigate("mine");
            }} /> : <PublishWorkspace meta={meta} onDraftPublished={refresh} onDone={() => {
              setModal(null);
              setToast("好物发布成功，已为有需要的同学进行匹配");
              refresh();
              navigate("mine");
            }} />)}
        </Modal>
      )}
      {modal === "wanted" && (
        <Modal
          title={editingWanted ? "编辑求购" : "告诉同学们，你在找什么"}
          onClose={() => {
            setModal(null);
            setEditingWanted(null);
            setPublishingIntent(null);
          }}
        >
          <WantedForm
            meta={meta}
            initial={query}
            editingWanted={editingWanted}
            initialIntent={publishingIntent}
            onDone={() => {
              setModal(null);
              setEditingWanted(null);
              refresh();
              navigate("mywanted");
              setPublishingIntent(null);
              setToast(editingWanted ? "求购与代蹲条件已同步更新" : "求购已发布，燕渡已开始替你代蹲");
            }}
          />
        </Modal>
      )}
      {modal === "feedback" && (
        <Modal title="意见反馈" onClose={() => setModal(null)}>
          <FeedbackCenter key={`${user?.id ?? "guest"}-${feedbackId ?? "new"}`} user={user}
            initialId={feedbackId} onChange={refresh}
            onLogin={() => { feedbackAfterLogin.current = true; setModal("login"); }} />
        </Modal>
      )}
      {modal === "notifications" && (
        <Modal
          title={noticeIntent ? "这个愿望发现的好物" : "燕渡为你捎来的消息"}
          onClose={() => setModal(null)}
        >
          {noticeIntent ? (
            <>
              <p className="hint">当前愿望：{noticeIntent.raw_query}</p>
              {taskNotices.loading ? (
                <p className="hint">正在查看这个愿望的匹配结果…</p>
              ) : taskNotices.error ? (
                <p role="alert">{taskNotices.error}</p>
              ) : visibleNotices.length ? (
                <div className="notice-list">
                  {visibleNotices.map(renderNotice)}
                </div>
              ) : (
                <Empty
                  title="这个愿望暂时没有匹配好物"
                  text="有符合这个愿望的好物时，会出现在这里。"
                  action="返回代蹲任务"
                  onAction={() => setModal(null)}
                />
              )}
            </>
          ) : (
            <div className="notice-center">
              {!!siteFeedbackNotices.data?.count && (
                <section className="notice-group">
                  <h3 className="notice-group-title">意见反馈回复</h3>
                  {siteFeedbackNotices.data.items.map((n) => (
                    <article className="notice unread" key={n.id}>
                      <strong>{n.body}</strong>
                      <button type="button" className="text-button" onClick={() => openFeedback(n.feedback_id)}>查看反馈与回复 →</button>
                    </article>
                  ))}
                </section>
              )}
                <section className="notice-group">
                  <h3 className="notice-group-title">公告与更新</h3>
                  <AnnouncementFeed key={user?.id ?? "guest"} userId={user?.id} revision={noticeRevision} compact />
                  <button
                    className="text-button"
                    onClick={() => {
                      setModal("announcements");
                    }}
                  >
                    历史公告
                    <ArrowRight size={14} />
                  </button>
                </section>
              {[summary.error, noticeResource.error, conversations.error, saleFeedbackMine.error, siteFeedbackNotices.error].filter(Boolean).length > 0 &&
                <p className="form-error" role="alert">部分通知暂时未能刷新。<button type="button" className="text-button" onClick={refresh}>重试</button></p>}
              {chatUnread > 0 && (
                <section className="notice-group">
                  <h3 className="notice-group-title">站内新消息</h3>
                  {(conversations.data ?? [])
                    .filter((c) => c.unread_count > 0)
                    .map((c) => (
                      <article className="notice unread" key={c.id}>
                        <div>
                          <span className="task-status">新消息</span>
                          <h3>{c.item_title}</h3>
                          <p>{c.last_message?.body}</p>
                        </div>
                        <button
                          className="text-button"
                          onClick={() => {
                            setModal(null);
                            location.hash = `messages/${c.id}`;
                            setView("messages");
                            setChatItem(null);
                            setChatDraft("");
                            setPendingConversation(c.id);
                          }}
                        >
                          去查看
                          <ArrowRight size={14} />
                        </button>
                      </article>
                    ))}
                </section>
              )}
              {feedbackPending > 0 && (
                <section className="notice-group">
                  <h3 className="notice-group-title">买家反馈已售 · {feedbackPending} 条待处理</h3>
                  {(saleFeedbackMine.data ?? []).map((f) => (
                    <article className={`notice ${f.is_read ? "" : "unread"}`} key={f.id}>
                      <ProductArt item={f.item} />
                      <div>
                        <span className="task-status">{f.is_read ? "已读 · 待处理" : "未读 · 反馈已售"}</span>
                        <h3>{f.item.title}</h3>
                        <p>
                          {f.reporter?.nickname ?? "买家"}反馈该商品可能已售，请核实。
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={async () => {
                          if (await openItem(f.item) && !f.is_read) void operate(() => api(`/sale-feedback/${f.id}/read`, "POST"));
                        }}
                      >
                        去处理
                        <ArrowRight size={14} />
                      </button>
                    </article>
                  ))}
                </section>
              )}
              {notices.length > 0 && (
                <section className="notice-group">
                  <h3 className="notice-group-title">代蹲匹配</h3>
                  <div className="notice-list">{notices.map(renderNotice)}</div>
                </section>
              )}
              {user && summary.data && allUnread === 0 && !summary.error && (
                <Empty
                  title="暂时没有新消息"
                  text="有新消息、匹配结果或买家反馈时会在这里提醒你。"
                  action="去许个愿"
                  onAction={() => {
                    setModal(null);
                    openForm("intent");
                  }}
                />
              )}
            </div>
          )}
        </Modal>
      )}
      {modal === "compare" && (
        <Modal
          title="哪一件，更适合你？"
          onClose={() => setModal(null)}
          style={{ width: `min(860px, ${compare.length * 280 + 60}px)` }}
        >
          <div
            className="comparison-grid"
            style={{
              gridTemplateColumns: `repeat(${compare.length}, minmax(0, 1fr))`,
            }}
          >
            {compare.map((i) => (
              <div key={i.id}>
                <button
                  className="text-button"
                  onClick={() => removeCompare(i.id)}
                  aria-label={`移除对比：${i.title}`}
                >
                  <X size={14} />
                  移除
                </button>
                <ProductArt item={i} />
                <h3>{i.title}</h3>
                <p className="price">¥{money(i.price)}</p>
                <dl>
                  <dt>成色</dt>
                  <dd>{i.condition_grade}</dd>
                  <dt>校区</dt>
                  <dd>{i.campus}</dd>
                  <dt>卖家描述</dt>
                  <dd>{i.description}</dd>
                  <dt>卖家评价</dt>
                  <dd>暂无评价数据</dd>
                </dl>
                <button
                  className="button secondary full"
                  onClick={() => void openItem(i)}
                >
                  查看最新状态
                </button>
              </div>
            ))}
          </div>
          <p className="hint">
            以上为加入对比时的商品信息，交易前请重新查看商品状态。
          </p>
        </Modal>
      )}
      {modal === "announcements" && (
        <Modal title="公告与更新" onClose={() => setModal(null)}>
          <AnnouncementFeed key={user?.id ?? "guest"} userId={user?.id} revision={noticeRevision} />
        </Modal>
      )}
      {modal === "detail" && selected && (
        <Modal title="好物详情" onClose={() => setModal(null)} style={{ width: 850 }}>
          {detailFromChat && <button type="button" className="text-button detail-chat-back" onClick={() => setModal(null)}><ChevronLeft size={16} />返回聊天</button>}
          <div className="detail-grid">
            <div>
              <ProductGallery key={selected.id} item={selected} />
              {selected.is_demo && (
                <p className="hint">演示商品插画，不代表真实在售商品。</p>
              )}
            </div>
            <div>
              <div className="detail-badges">
                <span className="category-label">{selected.category}</span>
                <span className="category-label">
                  {statusText[selected.status]}
                </span>
              </div>
              <h2 className="detail-title">{selected.title}</h2>
              <div className="detail-price">¥{money(selected.price)}</div>
              <div className="detail-meta">
                <span>
                  <MapPin size={15} />
                  {selected.campus}
                </span>
                <span>{selected.condition_grade}</span>
              </div>
              <p className="detail-description">{selected.description}</p>
              <div className="pills">
                {selected.tags.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
              <div className="seller-info">
                <span className="avatar">{selected.seller.nickname[0]}</span>
                <div>
                  <strong>{selected.seller.nickname}</strong>
                  <small>
                    {selected.is_demo ? "校园演示账号" : "平台用户"}
                  </small>
                  <SellerRating userId={selected.seller.id} onOpen={() => setModal("reviews")} />
                </div>
                <ShieldCheck size={20} />
              </div>
              {selected.is_owner ? (
                <div className="detail-actions">
                  {selected.sale_feedback_count > 0 && <p className="hint">{selected.sale_feedback_count} 位买家反馈商品可能已售。请核实后更新状态。</p>}
                  {saleFeedback.data?.map((feedback) => <div className="sale-feedback-row" key={feedback.id}>
                    <span>收到反馈：{new Date(feedback.created_at).toLocaleString("zh-CN")}</span>
                    <button className="text-button" disabled={busy} onClick={() => void operate(async () => {
                      setSelected(await api<Item>(`/items/${selected.id}/sale-feedback/${feedback.id}/review`, "POST", { action: "sold" }));
                    }, "已确认售出")}>确认已售</button>
                    <button className="text-button" disabled={busy} onClick={() => void operate(async () => {
                      setSelected(await api<Item>(`/items/${selected.id}/sale-feedback/${feedback.id}/review`, "POST", { action: "decline" }));
                    }, "已驳回反馈")}>仍在售</button>
                  </div>)}
                  {!["SOLD", "BANNED", "WITHDRAWN"].includes(selected.status) && (
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() => {
                        setCopiedDraft(null);
                        setPrefill(null);
                        setEditingItem(selected);
                        setModal("publish");
                      }}
                    >
                      编辑商品
                    </button>
                  )}
                  {["ACTIVE", "RESERVED", "EXPIRED", "SOLD"].includes(
                    selected.status,
                  ) && (
                    <>
                      {selected.can_relist && (
                        <button
                          className="button primary"
                          disabled={busy}
                          onClick={() =>
                            void operate(
                              async () =>
                                setSelected(
                                  await api<Item>(
                                    `/items/${selected.id}/status`,
                                    "PATCH",
                                    { status: "ACTIVE" },
                                  ),
                                ),
                              "商品已重新上架",
                            )
                          }
                        >
                          重新上架
                        </button>
                      )}
                      {selected.status === "ACTIVE" && (
                        <button
                          className="button secondary"
                          disabled={busy}
                          onClick={() =>
                            void operate(
                              async () =>
                                setSelected(
                                  await api<Item>(
                                    `/items/${selected.id}/status`,
                                    "PATCH",
                                    { status: "RESERVED" },
                                  ),
                                ),
                              "已标记为预订",
                            )
                          }
                        >
                          标记预订
                        </button>
                      )}
                      {["ACTIVE", "RESERVED"].includes(selected.status) && (
                        <button
                          className="button primary"
                          disabled={busy}
                          onClick={() =>
                            void operate(
                              async () =>
                                setSelected(
                                  await api<Item>(
                                    `/items/${selected.id}/status`,
                                    "PATCH",
                                    { status: "SOLD" },
                                  ),
                                ),
                              "已标记售出",
                            )
                          }
                        >
                          标记已售出
                        </button>
                      )}
                    </>
                  )}
                  {selected.can_duplicate && <button className="button primary" disabled={busy} onClick={() => void operate(async () => {
                    const draft = await api<ItemDraft>(`/items/${selected.id}/duplicate`, "POST");
                    setCopiedDraft(draft);
                    setEditingItem(null);
                    setPrefill(null);
                    setModal("publish");
                  })}><Copy size={16} />再发一件</button>}
                  {selected.can_withdraw && <button className="button secondary" disabled={busy} onClick={() => {
                    if (!window.confirm(`撤回「${selected.title}」？撤回后不会公开展示，已有交易和聊天记录会保留，且不能直接重新上架。`)) return;
                    void operate(async () => {
                      const item = await api<Item>(`/items/${selected.id}`, "DELETE");
                      setSelected(item);
                      setCompare((current) => current.filter((entry) => entry.id !== item.id));
                    }, "商品已撤回，聊天记录仍可查看");
                  }}>撤回商品</button>}
                  {selected.status === "WITHDRAWN" && <p className="hint">商品已撤回，已有交易和聊天记录已保留。</p>}
                  {["ACTIVE", "RESERVED", "SOLD"].includes(selected.status) && selected.can_withdraw === false && <p className="hint">请先处理预订或待确认交易，再撤回商品。</p>}
                </div>
              ) : (
                <div className="detail-actions">
                  {["ACTIVE", "RESERVED"].includes(selected.status) && <button className="button secondary" disabled={busy}
                    onClick={() => { if (!needUser()) return; void operate(
                      () => api(`/items/${selected.id}/sale-feedback`, "POST"),
                      "已通知卖家核实商品是否售出"); }}><Flag size={16} />反馈已售</button>}
                  <button
                    className="button secondary"
                    onClick={() => favorite(selected)}
                  >
                    <Heart
                      size={17}
                      fill={selected.is_favorite ? "currentColor" : "none"}
                    />
                    {selected.is_favorite ? "已收藏" : "收藏"}
                  </button>
                  <button className="button primary" disabled={!detailFromChat && selected.status !== "ACTIVE"}
                    onClick={() => {
                      if (detailFromChat) { setModal(null); return; }
                      if (!needUser()) return;
                      setChatItem(selected); setChatDraft(""); setModal(null); navigate("messages");
                    }}>
                    <MessageCircle size={16} />{detailFromChat ? "返回聊天" : "联系卖家"}
                  </button>
                </div>
              )}
              <div className="detail-links">
                <button
                  onClick={() =>
                    void copy(
                      `${location.origin}/?item=${selected.id}`,
                      "商品链接已复制",
                    )
                  }
                >
                  <Share2 size={14} />
                  复制分享链接
                </button>
                <button
                  onClick={() => {
                    if (needUser()) {
                      setReporting(!reporting);
                    }
                  }}
                >
                  <Flag size={14} />
                  举报问题
                </button>
              </div>
            </div>
          </div>
          {similar.length > 0 && <section className="similar-items" aria-label="相似好物">
            <div className="similar-heading">
              <h3>相似好物</h3>
              <span>按分类、标签与价格为你挑选</span>
            </div>
            <div className="similar-grid">
              {similar.map((item) => (
                <button type="button" className="similar-card" key={item.id}
                  onClick={() => void openItem(item)} aria-label={`查看相似商品：${item.title}`}>
                  <ProductArt item={item} />
                  <strong>{item.title}</strong>
                  <span>¥{money(item.price)} · {item.campus}</span>
                </button>
              ))}
            </div>
          </section>}
          {reporting && (
            <form
              className="stack-form report-form"
              onSubmit={(e) => {
                e.preventDefault();
                void operate(async () => {
                  await api(`/items/${selected.id}/reports`, "POST", {
                    reason: reportText,
                  });
                  setReporting(false);
                }, "举报已提交，等待管理员核实");
              }}
            >
              <label>
                请描述遇到的问题
                <textarea
                  ref={reportRef}
                  value={reportText}
                  onChange={(e) => setReportText(e.target.value)}
                  required
                  minLength={5}
                  maxLength={1000}
                  placeholder="描述具体情况，方便管理员核实。"
                />
              </label>
              <button className="button secondary" disabled={busy}>
                提交举报
              </button>
              <button
                type="button"
                className="text-button"
                onClick={() => setReporting(false)}
              >
                取消举报
              </button>
            </form>
          )}
        </Modal>
      )}
      {modal === "reviews" && selected && (
        <Modal title={`${selected.seller.nickname}的交易评价`} onClose={() => setModal("detail")} style={{ width: 720 }}>
          <UserReviewsPanel userId={selected.seller.id} />
        </Modal>
      )}
      {sessionExpired && user && !recoverSession && <div className="session-expired-banner" role="status">
        <span>登录已过期，当前填写内容已保留。</span>
        <button className="button primary" onClick={() => setRecoverSession(true)}>重新登录</button>
      </div>}
      {recoverSession && user && <SessionRecovery user={user} meta={meta}
        onClose={() => setRecoverSession(false)} onRecovered={(account) => {
          setUser(account);
          setSessionEpoch((n) => n + 1);
          setSessionExpired(false);
          setRecoverSession(false);
          setToast("已重新登录，可继续刚才的操作");
        }} />}
    </div>
  );
}

type AdminView = "admin" | "admin-chat" | "admin-reports" | "admin-logs" | "admin-feedback" | "admin-metrics";

const adminTabs = [
  { key: "admin", label: "公告管理" },
  { key: "admin-metrics", label: "商业指标与访客" },
  { key: "admin-chat", label: "聊天举报" },
  { key: "admin-reports", label: "商品举报" },
  { key: "admin-feedback", label: "用户反馈" },
  { key: "admin-logs", label: "操作记录" },
] as const;

function AdminNav({
  view,
  onNavigate,
  counts,
}: {
  view: AdminView;
  onNavigate: (view: AdminView) => void;
  counts?: AdminSummary | null;
}) {
  return (
    <nav className="profile-nav" aria-label="审核工作台导航">
      {adminTabs.map(({ key, label }) => {
        const badge = key === "admin-reports" ? counts?.reports
          : key === "admin-chat" ? counts?.chat_reports
            : key === "admin-feedback" ? counts?.feedback
              : 0;
        return (
          <button
            key={key}
            className={view === key ? "active" : ""}
            onClick={() => onNavigate(key)}
          >
            {label}
            {!!badge && <span className="admin-nav-badge">{badge}</span>}
          </button>
        );
      })}
    </nav>
  );
}

function Admin({
  user,
  revision,
  refresh,
  notify,
  view,
}: {
  user: User | null;
  revision: number;
  refresh: () => void;
  notify: (v: string) => void;
  view: AdminView;
}) {
  const reports = useResource<Report[]>(
    "/admin/reports",
    revision,
    user?.role === "admin",
  );
  const logs = useResource<Log[]>(
    "/admin/logs",
    revision,
    user?.role === "admin",
  );
  const chatReports = useResource<ChatReport[]>(
    "/admin/chat-reports", revision, user?.role === "admin",
  );
  const adminAnnouncements = useResource<AdminAnnouncement[]>(
    "/admin/announcements", revision, user?.role === "admin",
  );
  const userGrowth = useResource<{
    total_users: number;
    base_count: number;
    trend: { date: string; new_users: number; cumulative_users: number }[];
  }>("/admin/analytics/user-growth", revision, user?.role === "admin" && view === "admin-metrics");
  const visitorFunnel = useResource<{
    total_unique_visitors: number;
    unregistered_browsers: number;
    funnel: { stage: string; count: number; pct: number }[];
    friction_drop_off_pct: number;
  }>("/admin/analytics/visitor-funnel", revision, user?.role === "admin" && view === "admin-metrics");
  const businessOverview = useResource<BusinessOverviewData>(
    "/admin/analytics/business-overview",
    revision,
    user?.role === "admin" && view === "admin-metrics"
  );
  const [busy, setBusy] = useState(false);
  const [showHandledReports, setShowHandledReports] = useState(false);
  const [annTitle, setAnnTitle] = useState("");
  const [annKind, setAnnKind] = useState<"公告" | "更新">("公告");
  const [annBody, setAnnBody] = useState("");
  if (user?.role !== "admin")
    return (
      <Empty
        title="这里需要管理员权限"
        text="登录管理员演示账号后，可以查看举报和操作记录。"
      />
    );
  async function review(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await api(`/admin/reports/${id}/review`, "POST", {
        action: data.get("action"),
        note: data.get("note"),
        confirmed: data.get("confirmed") === "on",
      });
      notify("处理结果已保存，并已记录审核日志");
      form.reset();
      refresh();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reviewChat(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await api(`/admin/chat-reports/${id}/review`, "POST", {
        action: data.get("action"), note: data.get("note"), confirmed: data.get("confirmed") === "on",
      });
      notify("聊天举报已处理"); form.reset(); refresh();
    } catch (cause) { notify((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function createAnnouncement(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const title = annTitle.trim();
    const body = annBody.trim();
    if (title.length < 2 || body.length < 5) {
      notify("公告标题至少 2 字，内容至少 5 字");
      return;
    }
    setBusy(true);
    try {
      await api("/admin/announcements", "POST", { title, body, kind: annKind });
      notify("公告已发布");
      setAnnTitle("");
      setAnnBody("");
      refresh();
    } catch (cause) {
      notify((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggleAnnouncement(a: AdminAnnouncement) {
    setBusy(true);
    try {
      await api(`/admin/announcements/${a.id}`, "PATCH", { active: !a.active });
      notify(a.active ? "公告已下线" : "公告已上线");
      refresh();
    } catch (cause) {
      notify((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function deleteAnnouncement(a: AdminAnnouncement) {
    if (!window.confirm(`删除公告「${a.title}」？删除后无法恢复。`)) return;
    setBusy(true);
    try {
      await api(`/admin/announcements/${a.id}`, "DELETE");
      notify("公告已删除");
      refresh();
    } catch (cause) {
      notify((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visibleReports = (reports.data ?? []).filter((report) => showHandledReports || report.status === "OPEN");
  const handledReports = (reports.data ?? []).filter((report) => report.status !== "OPEN").length;
  if (view === "admin-feedback") return <FeedbackWorkspace key={user.id} admin onChange={refresh} />;
  return (
    <>
      <Intro
        kicker="A COMMUNITY WE CARE FOR"
        title="审核工作台"
        text="规则整理线索，管理员核实事实。每一次操作都有据可查。"
      />
      <div className="info-strip">
        <ShieldCheck size={18} />
        当前仅提供文字风险词与同名商品检查，不包含图片识别。举报本身不代表违规成立。
      </div>
      {view === "admin" && (
        <>
          <h2 className="audit-title">公告管理</h2>
      <form className="stack-form" onSubmit={(e) => void createAnnouncement(e)}>
        <label>
          公告标题
          <input
            value={annTitle}
            onChange={(e) => setAnnTitle(e.target.value)}
            maxLength={200}
            placeholder="例如：「燕渡」上线通知"
          />
        </label>
        <label>
          公告类型
          <select
            value={annKind}
            onChange={(e) => setAnnKind(e.target.value as "公告" | "更新")}
          >
            <option value="公告">公告</option>
            <option value="更新">更新</option>
          </select>
        </label>
        <label>
          公告内容
          <textarea
            value={annBody}
            onChange={(e) => setAnnBody(e.target.value)}
            rows={7}
            maxLength={5000}
            placeholder="输入公告正文，支持换行"
          />
        </label>
        <button className="button primary" disabled={busy}>
          发布公告
        </button>
      </form>
      {adminAnnouncements.error && (
        <p className="form-error">{adminAnnouncements.error}</p>
      )}
      <div className="audit-list">
        {adminAnnouncements.data?.map((a) => (
          <div key={a.id}>
            <span>{new Date(a.created_at).toLocaleString("zh-CN")}</span>
            <strong>{a.title}</strong>
            <code>
              {a.kind}
              {a.active ? "" : " · 已下线"}
            </code>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void toggleAnnouncement(a)}
            >
              {a.active ? "下线" : "上线"}
            </button>
            <button
              className="text-button danger"
              disabled={busy}
              onClick={() => void deleteAnnouncement(a)}
            >
              删除
            </button>
          </div>
        ))}
      </div>
        </>
      )}
      {view === "admin-chat" && (
        <>
          <h2 className="audit-title">聊天消息举报</h2>
      {chatReports.error && <p className="form-error">{chatReports.error}</p>}
      {chatReports.data?.filter((r) => r.status === "OPEN").map((r) => <article className="review-card" key={r.id}>
        <h3>{r.item_title} · {r.sender.nickname}</h3>
        <p>被举报消息：{r.message_body || "[图片]"}</p>
        <div className="chat-images">{r.message_images.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer"><img src={url} alt="被举报的聊天图片" /></a>)}</div>
        <p>举报原因：{r.reason}</p>
        <form className="review-form" onSubmit={(e) => void reviewChat(e, r.id)}>
          <label>处理方式<select name="action"><option value="dismiss">不采纳举报</option><option value="hide">隐藏消息</option></select></label>
          <label>审核依据<input name="note" required minLength={5} maxLength={500} placeholder="写下核实结果" /></label>
          <label className="check-label"><input type="checkbox" name="confirmed" required />我已核实，确认处理</label>
          <button className="button primary" disabled={busy}>确认处理</button>
        </form>
      </article>)}
        </>
      )}
      {view === "admin-reports" && (
        <>
          <div className="admin-heading-row">
            <h2 className="audit-title">商品举报</h2>
            <button type="button" className="button secondary" disabled={busy}
              onClick={() => setShowHandledReports((value) => !value)}>
              {showHandledReports ? "只看待处理" : `显示已处理${handledReports ? ` (${handledReports})` : ""}`}
            </button>
          </div>
      {reports.loading ? (
        <Busy />
      ) : reports.error ? (
        <Empty
          title="审核记录加载失败"
          text={reports.error}
          action="重试"
          onAction={refresh}
        />
      ) : visibleReports.length ? (
        <div className="review-list">
          {visibleReports.map((r) => (
            <article className="review-card" key={r.id}>
              <div className="section-heading">
                <h3>{r.item.title}</h3>
                <span className="category-label">
                  {r.status} · 风险：{r.risk}
                </span>
              </div>
              <p>举报内容：{r.reason}</p>
              <ul>
                {r.evidence.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
              <form
                className="review-form"
                onSubmit={(e) => void review(e, r.id)}
              >
                <label>
                  处理方式
                  <select name="action">
                    <option value="dismiss">不采纳举报</option>
                    <option value="hide">隐藏商品</option>
                    <option value="restore">恢复被隐藏商品</option>
                  </select>
                </label>
                <label>
                  审核依据
                  <input
                    name="note"
                    required
                    minLength={5}
                    maxLength={500}
                    placeholder="请记录核实结果和依据"
                  />
                </label>
                <label className="check-label">
                  <input type="checkbox" name="confirmed" required />
                  我已核实，确认执行此操作
                </label>
                <button className="button primary" disabled={busy}>
                  确认处理
                </button>
              </form>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="目前没有待核实的举报"
          text="收到新的举报后，相关证据会整理在这里。"
        />
      )}
        </>
      )}
      {view === "admin-metrics" && (
        <AdminMetrics
          growthData={userGrowth.data ?? null}
          funnelData={visitorFunnel.data ?? null}
          businessData={businessOverview.data ?? null}
          error={userGrowth.error || visitorFunnel.error || businessOverview.error}
        />
      )}
      {view === "admin-logs" && (
        <>
          <h2 className="audit-title">最近操作记录</h2>
      {logs.error && <p className="form-error">{logs.error}</p>}
      <div className="audit-list">
        {logs.data?.map((l) => (
          <div key={l.id}>
            <span>{new Date(l.created_at).toLocaleString("zh-CN")}</span>
            <strong>{l.actor.nickname}</strong>
            <code>{l.action}</code>
            <span>{l.detail || l.target_id.slice(0, 12)}</span>
          </div>
        ))}
      </div>
        </>
      )}
    </>
  );
}
