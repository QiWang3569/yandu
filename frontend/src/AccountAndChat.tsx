import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Flag, ImagePlus, LockKeyhole, Mail, MessageCircle, Send, ShieldOff, Sparkles, Trash2, X } from "lucide-react";
import { api, statusText, type ChatMessage, type Conversation, type Item, type Meta, type TradeReview, type User } from "./api";
import { Empty, Modal, ProductArt } from "./components";
import { REVIEW_TAGS, Stars } from "./Reviews";

const passwordValid = (value: string) => value.length >= 9 && value.length <= 128 && /[A-Za-z]/.test(value) && /[0-9]/.test(value);

function PasswordRules({ value }: { value: string }) {
  return <div className="password-rules" aria-label="密码要求">
    <span className={value.length >= 9 && value.length <= 128 ? "met" : ""}>9–128 位</span>
    <span className={/[A-Za-z]/.test(value) ? "met" : ""}>英文字母</span>
    <span className={/[0-9]/.test(value) ? "met" : ""}>数字</span>
  </div>;
}

export function EmailSignIn({ meta, intent, email, setEmail, code, setCode, sent, setSent, onSignedIn }: {
  meta: Meta; intent: "register" | "login"; email: string; setEmail: (email: string) => void;
  code: string; setCode: (code: string) => void; sent: boolean; setSent: (sent: boolean) => void;
  onSignedIn: (user: User) => void;
}) {
  const [nickname, setNickname] = useState("");
  const [campus, setCampus] = useState("燕园校本部");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (intent === "register") {
      if (!passwordValid(password)) { setError("密码需为 9–128 位，且同时包含英文字母和数字"); return; }
      if (password !== confirm) { setError("两次输入的密码不一致"); return; }
    }
    setBusy(true);
    setError("");
    try {
      if (!sent) {
        await api("/auth/email/request-code", "POST", { email });
        setSent(true);
      } else {
        const result = await api<{ user: User }>("/auth/email/verify", "POST", {
          email, code, intent, ...(intent === "register" ? { nickname, campus, password } : {}),
        });
        onSignedIn(result.user);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="stack-form email-sign-in" onSubmit={(event) => void submit(event)}>
      <p className="auth-description">{intent === "register"
        ? "填写资料并设置密码，再用北大邮箱验证码完成注册。"
        : "已经有账号？收取一次性验证码即可登录。"}</p>
      <div className="auth-steps" aria-label="操作步骤"><span className="current">1 · {intent === "register" ? "填写账号" : "填写邮箱"}</span><span className={sent ? "current" : ""}>2 · 验证邮箱</span></div>
      <label>
        北大邮箱
        <input type="email" autoComplete="email" required value={email}
          disabled={sent || busy} placeholder="@pku.edu.cn 或 @stu.pku.edu.cn"
          onChange={(event) => setEmail(event.target.value)} />
      </label>
      {intent === "register" && <><div className="form-grid">
          <label>
            昵称
            <input value={nickname} required minLength={2} maxLength={50} onChange={(event) => setNickname(event.target.value)} />
          </label>
          <label>
            校区
            <select value={campus} onChange={(event) => setCampus(event.target.value)}>
              {meta.campuses.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
        </div>
        <label>设置密码<input type="password" autoComplete="new-password" required minLength={9} maxLength={128}
          value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <PasswordRules value={password} />
        <label>确认密码<input type="password" autoComplete="new-password" required minLength={9} maxLength={128}
          value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label></>}
      {sent && <>
        <p className="hint" role="status">验证码已发送至 {email}，10 分钟内有效。</p>
        <label>
          8 位验证码
          <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}"
            required value={code} onChange={(event) => setCode(event.target.value)} />
        </label>
        <button type="button" className="text-button auth-change-email" onClick={() => { setSent(false); setCode(""); setError(""); }}>
          更换邮箱或重新获取验证码
        </button>
      </>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {!meta.email_auth_ready && <p className="form-error">邮件服务尚未配置，邮箱验证暂不可用。</p>}
      {intent === "register" && <p className="hint">注册后默认接收未读站内信邮件提醒，可在个人主页关闭。</p>}
      <button type="submit" className="button primary full" disabled={busy || !meta.email_auth_ready}>
        <Mail size={16} />{busy ? "处理中…" : sent ? intent === "register" ? "创建账号" : "验证并登录" : "发送验证码"}
      </button>
    </form>
  );
}

export function AuthMethods({ meta, onSignedIn, initialMode = "register", initialEmail = "" }: {
  meta: Meta; onSignedIn: (user: User) => void; initialMode?: "register" | "code" | "password"; initialEmail?: string;
}) {
  const [mode, setMode] = useState<"register" | "code" | "password" | "reset">(initialMode);
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  return <div className="auth-methods">
    <div className="auth-tabs" role="tablist" aria-label="账号入口">
      <button type="button" id="auth-register" role="tab" aria-controls="auth-panel" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""}
        onClick={() => setMode("register")}>注册账号</button>
      <button type="button" id="auth-code" role="tab" aria-controls="auth-panel" aria-selected={mode === "code"} className={mode === "code" ? "active" : ""}
        onClick={() => setMode("code")}>验证码登录</button>
      <button type="button" id="auth-password" role="tab" aria-controls="auth-panel" aria-selected={mode === "password" || mode === "reset"} className={mode === "password" || mode === "reset" ? "active" : ""}
        onClick={() => { setMode("password"); setSent(false); setCode(""); }}>密码登录</button>
    </div>
    <div role="tabpanel" id="auth-panel" aria-labelledby={`auth-${mode === "reset" ? "password" : mode}`}>
    {mode === "register" && <EmailSignIn key="register" meta={meta} intent="register" email={email} setEmail={setEmail}
      code={code} setCode={setCode} sent={sent} setSent={setSent} onSignedIn={onSignedIn} />}
    {mode === "code" && <EmailSignIn key="login" meta={meta} intent="login" email={email} setEmail={setEmail}
      code={code} setCode={setCode} sent={sent} setSent={setSent} onSignedIn={onSignedIn} />}
    {mode === "password" && <PasswordSignIn email={email} setEmail={setEmail} onSignedIn={onSignedIn} onReset={() => setMode("reset")} />}
    {mode === "reset" && <>
      <button type="button" className="text-button auth-back" onClick={() => setMode("password")}>← 返回密码登录</button>
      <PasswordSetup meta={meta} onSignedIn={onSignedIn} />
    </>}
    </div>
  </div>;
}

function PasswordSignIn({ email, setEmail, onSignedIn, onReset }: {
  email: string; setEmail: (email: string) => void; onSignedIn: (user: User) => void; onReset: () => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ user: User }>("/auth/password/login", "POST", { email, password });
      onSignedIn(result.user);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return <form className="stack-form email-sign-in" onSubmit={(event) => void submit(event)}>
    <p className="auth-description">已设置密码的北大邮箱账号，可以直接登录。</p>
    <label>北大邮箱<input type="email" autoComplete="username" required maxLength={254} value={email}
        placeholder="@pku.edu.cn 或 @stu.pku.edu.cn" onChange={(event) => setEmail(event.target.value)} /></label>
    <label>登录密码<input type="password" autoComplete="current-password" required maxLength={128} value={password}
      onChange={(event) => setPassword(event.target.value)} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="button primary full" type="submit" disabled={busy}><LockKeyhole size={16} />{busy ? "登录中…" : "使用密码登录"}</button>
    <button type="button" className="text-button auth-reset-link" onClick={onReset}>首次设置或忘记密码？用邮箱验证码设置</button>
  </form>;
}

export function PasswordSetup({ meta, initialEmail = "", onSignedIn }: {
  meta: Meta; initialEmail?: string; onSignedIn: (user: User) => void;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (sent && !passwordValid(password)) { setError("密码需为 9–128 位，且同时包含英文字母和数字"); return; }
    if (sent && password !== confirm) { setError("两次输入的密码不一致"); return; }
    setBusy(true);
    try {
      if (!sent) {
        await api("/auth/email/request-code", "POST", { email });
        setSent(true);
      } else {
        const result = await api<{ user: User }>("/auth/password/set", "POST", { email, code, password });
        onSignedIn(result.user);
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return <form className="stack-form email-sign-in" onSubmit={(event) => void submit(event)}>
    <p className="auth-description">验证北大邮箱后设置新密码。完成后，其他设备上的登录会失效。</p>
    <label>北大邮箱<input type="email" autoComplete="email" required maxLength={254} value={email}
      disabled={sent || busy || !!initialEmail} placeholder="@pku.edu.cn 或 @stu.pku.edu.cn"
      onChange={(event) => setEmail(event.target.value)} /></label>
    {sent && <>
      <p className="hint" role="status">验证码已发送至 {email}，10 分钟内有效。</p>
      <label>8 位验证码<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}" required
        value={code} onChange={(event) => setCode(event.target.value)} /></label>
      <label>新密码<input type="password" autoComplete="new-password" required minLength={9}
        maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <PasswordRules value={password} />
      <label>确认新密码<input type="password" autoComplete="new-password" required minLength={9} maxLength={128}
        value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>
      <button type="button" className="text-button" onClick={() => { setSent(false); setCode(""); }}>重新获取验证码</button>
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {!meta.email_auth_ready && <p className="form-error">邮件服务尚未配置，暂时无法设置或重置密码。</p>}
    <button className="button primary full" type="submit" disabled={busy || !meta.email_auth_ready}>
      <LockKeyhole size={16} />{busy ? "处理中…" : sent ? "验证并保存密码" : "发送验证码"}
    </button>
  </form>;
}

export function ChatCenter({ user, conversations, initialItem, initialDraft, initialConversationId, onConversationOpened, onStarted, onOpenItem, refresh }: {
  user: User;
  conversations: Conversation[];
  initialItem: Item | null;
  initialDraft: string;
  initialConversationId?: string | null;
  onConversationOpened?: () => void;
  onStarted: () => void;
  onOpenItem: (id: string) => void;
  refresh: () => void;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [recentConversation, setRecentConversation] = useState<Conversation | null>(null);
  const activeSnapshot = useRef<Conversation | null>(null);
  const [newItem, setNewItem] = useState<Item | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadedOlder, setLoadedOlder] = useState(false);
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [imageView, setImageView] = useState<string | null>(null);
  const uploadEpoch = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviews, setReviews] = useState<TradeReview[]>([]);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewBody, setReviewBody] = useState("");
  const [reviewTags, setReviewTags] = useState<string[]>([]);
  const [reviewsOpen, setReviewsOpen] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reportMessageId, setReportMessageId] = useState<string | null>(null);
  const [reportReason, setReportReason] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [layoutHeight, setLayoutHeight] = useState<number>();
  const loadingOlder = useRef(false);
  const handledItem = useRef<string | null>(null);
  useEffect(() => {
    if (!initialConversationId) return;
    let alive = true;
    setActiveId(null);
    setRecentConversation(null);
    setNewItem(null);
    setMessages([]);
    setError("");
    void api<Conversation>(`/conversations/${encodeURIComponent(initialConversationId)}`)
      .then((conversation) => {
        if (!alive) return;
        setActiveId(conversation.id);
        setRecentConversation(conversation);
        setLoadedOlder(false);
        setDraft("");
        onConversationOpened?.();
      })
      .catch(() => {
        if (!alive) return;
        setError("无法打开该会话，请确认登录了接收提醒的账号后重试。");
        onConversationOpened?.();
      });
    return () => { alive = false; };
  }, [initialConversationId, user.id, onConversationOpened]);
  useEffect(() => {
    const measure = () => {
      const layout = layoutRef.current;
      if (!layout) return;
      const top = layout.getBoundingClientRect().top + window.scrollY;
      const navigation = window.innerWidth <= 650 ? document.querySelector(".sidebar")?.getBoundingClientRect().height ?? 62 : 0;
      const viewport = window.visualViewport?.height ?? window.innerHeight;
      setLayoutHeight(Math.max(360, Math.min(1080, viewport - top - navigation - 16)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    for (const element of document.querySelectorAll(".chat-heading, .profile-nav")) observer.observe(element);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); window.visualViewport?.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => {
    uploadEpoch.current += 1;
    setImages([]);
    setUploading(false);
    setImageView(null);
  }, [activeId, newItem?.id]);
  useEffect(() => {
    if (!initialItem) { handledItem.current = null; return; }
    if (handledItem.current === initialItem.id) return;
    handledItem.current = initialItem.id;
    const existing = conversations.find((conversation) => conversation.item_id === initialItem.id);
    if (existing) {
      setActiveId(existing.id);
      setRecentConversation(existing);
      setNewItem(null);
      setMessages([]);
    } else {
      setActiveId(null);
      setNewItem(initialItem);
      setMessages([]);
    }
    setLoadedOlder(false);
    setDraft(initialDraft);
  }, [initialItem, initialDraft, conversations]);
  useEffect(() => {
    if (!activeId) return;
    let alive = true;
    let loading = false;
    async function load() {
      if (loading || document.visibilityState !== "visible") return;
      loading = true;
      try {
        const result = await api<{ messages: ChatMessage[]; has_more: boolean }>(`/conversations/${activeId}/messages`);
        if (!alive) return;
        setMessages((current) => {
          if (current.length <= result.messages.length) return result.messages;
          const merged = new Map([...current, ...result.messages].map((message) => [message.id, message]));
          return [...merged.values()].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
        });
        if (!loadedOlder) setHasMore(result.has_more);
        setError("");
        const ids = result.messages.filter((message) => message.sender_id !== user.id && !message.read_at).map((message) => message.id);
        if (ids.length && document.visibilityState === "visible" && !document.querySelector('[aria-modal="true"]')) {
          await api(`/conversations/${activeId}/read`, "POST", { ids });
          if (alive) refresh();
        }
      } catch (cause) {
        if (alive) setError((cause as Error).message);
      } finally { loading = false; }
    }
    void load();
    const timer = window.setInterval(() => void load(), 8000);
    const visible = () => { void load(); };
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("focus", visible);
    return () => { alive = false; clearInterval(timer); document.removeEventListener("visibilitychange", visible); window.removeEventListener("focus", visible); };
  }, [activeId, user.id, refresh, loadedOlder]);
  useEffect(() => {
    if (loadingOlder.current) { loadingOlder.current = false; return; }
    const history = bottom.current?.parentElement;
    if (history) history.scrollTop = history.scrollHeight;
  }, [activeId, messages.length]);
  const listedConversation = conversations.find((conversation) => conversation.id === activeId) ?? null;
  useEffect(() => {
    if (listedConversation && recentConversation?.id === listedConversation.id &&
      listedConversation.deal_status === recentConversation.deal_status &&
      listedConversation.blocked === recentConversation.blocked &&
      listedConversation.blocked_by_me === recentConversation.blocked_by_me) {
      setRecentConversation(null);
    }
  }, [listedConversation, recentConversation]);
  const active = (recentConversation?.id === activeId ? recentConversation : listedConversation)
    ?? (activeSnapshot.current?.id === activeId ? activeSnapshot.current : null);
  // Keep the thread mounted while its list is being refreshed after a message or deal action.
  if (active) activeSnapshot.current = active;
  useEffect(() => {
    setReviewsOpen(false);
    setReviewBody("");
    setReviewTags([]);
    setReviewRating(5);
    setReviews([]);
    if (!activeId) return;
    let alive = true;
    const read = () => {
      void api<{ reviews: TradeReview[] }>(`/conversations/${activeId}/reviews`)
        .then((result) => { if (alive) setReviews(result.reviews); })
        .catch(() => { if (alive) setReviews([]); });
    };
    read();
    // A confirmed chat polls slowly so the counterpart's review shows up without reload.
    const timer = active?.deal_status === "CONFIRMED" ? window.setInterval(read, 30000) : undefined;
    return () => { alive = false; if (timer !== undefined) clearInterval(timer); };
  }, [activeId, active?.deal_status]);
  async function changeDeal(action: "request" | "reserve" | "decline" | "cancel" | "sold" | "confirm") {
    if (!activeId) return;
    setBusy(true); setError("");
    try {
      const result = await api<Conversation>(`/conversations/${activeId}/deal`, "POST", { action: action.toLowerCase() });
      setRecentConversation(result); refresh();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function toggleBlock() {
    if (!activeId || !active) return;
    setBusy(true); setError("");
    try {
      await api(`/conversations/${activeId}/block`, active.blocked_by_me ? "DELETE" : "POST");
      setRecentConversation({ ...active, blocked_by_me: !active.blocked_by_me,
        blocked: !active.blocked_by_me || (active.blocked && !active.blocked_by_me) });
      refresh();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function deleteConversation() {
    if (!activeId || busy) return;
    if (!window.confirm("从你的会话列表移除这次聊天？对方发来新消息时会重新出现，交易和举报记录仍会保留。")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`/conversations/${activeId}`, "DELETE");
      setActiveId(null);
      setRecentConversation(null);
      setMessages([]);
      setReviews([]);
      setNotice("会话已从列表移除。对方发来新消息后，会自动重新出现。");
      refresh();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  function toggleReviewTag(tag: string) {
    setReviewTags((current) => current.includes(tag)
      ? current.filter((entry) => entry !== tag)
      : [...current, tag]);
  }
  async function submitReview(event: FormEvent) {
    event.preventDefault();
    if (!activeId || reviewBusy) return;
    setReviewBusy(true); setError("");
    try {
      const review = await api<TradeReview>(`/conversations/${activeId}/reviews`, "POST", {
        rating: reviewRating, body: reviewBody, tags: reviewTags,
      });
      setReviews((current) => [...current, review]);
      setReviewRating(5);
      setReviewBody("");
      setReviewTags([]);
      refresh();
    } catch (cause) { setError((cause as Error).message); }
    finally { setReviewBusy(false); }
  }
  async function submitReport(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !reportMessageId) return;
    setBusy(true); setError("");
    try {
      await api(`/conversations/${activeId}/messages/${reportMessageId}/reports`, "POST", { reason: reportReason });
      setReportMessageId(null); setReportReason("");
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (busy || uploading || (!draft.trim() && !images.length) || (!activeId && !newItem)) return;
    setBusy(true);
    setError("");
    try {
      if (activeId) {
        const message = await api<ChatMessage>(`/conversations/${activeId}/messages`, "POST", { body: draft, images });
        setMessages((current) => [...current, message]);
      } else if (newItem) {
        const result = await api<{ conversation: Conversation; message: ChatMessage }>(
          `/items/${newItem.id}/conversations`, "POST", { body: draft, images });
        setActiveId(result.conversation.id);
        setRecentConversation(result.conversation);
        setNewItem(null);
        setMessages([result.message]);
        onStarted();
      }
      setDraft("");
      setImages([]);
      refresh();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function uploadImages(files: FileList | null) {
    if (!files?.length || uploading || busy || active?.blocked) return;
    if (images.length + files.length > 3) { setError("每条消息最多添加 3 张图片"); return; }
    const epoch = uploadEpoch.current;
    setUploading(true); setError("");
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("file", file);
        const result = await api<{ url: string }>("/chat-uploads", "POST", body);
        if (epoch !== uploadEpoch.current) return;
        setImages((current) => [...current, result.url]);
      }
    } catch (cause) {
      if (epoch === uploadEpoch.current) setError((cause as Error).message);
    } finally {
      if (epoch === uploadEpoch.current) setUploading(false);
    }
  }
  async function loadOlder() {
    if (!activeId || !messages.length) return;
    try {
      const result = await api<{ messages: ChatMessage[]; has_more: boolean }>(
        `/conversations/${activeId}/messages?before_id=${encodeURIComponent(messages[0].id)}`);
      loadingOlder.current = result.messages.length > 0;
      setMessages((current) => [...result.messages, ...current]);
      setHasMore(result.has_more);
      setLoadedOlder(true);
      const ids = result.messages.filter((message) => message.sender_id !== user.id && !message.read_at).map((message) => message.id);
      if (ids.length && document.visibilityState === "visible") {
        await api(`/conversations/${activeId}/read`, "POST", { ids });
        refresh();
      }
    } catch (cause) { setError((cause as Error).message); }
  }
  async function generateDraft() {
    if (!newItem) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ draft: string }>(
        `/items/${newItem.id}/message-draft`,
        "POST",
      );
      setDraft(result.draft);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const myReview = reviews.find((review) => review.reviewer_id === user.id) ?? null;
  const counterpartReview = reviews.find((review) => review.reviewer_id !== user.id) ?? null;
  const canDeleteConversation = !!active && !["REQUESTED", "RESERVED", "SOLD"].includes(active.deal_status);
  return (
    <section className="chat-page">
      <div className="chat-heading"><MessageCircle size={22} /><div><h1>站内消息</h1><p>关于商品的沟通会保存在这里，只有买卖双方可见。</p></div></div>
      {notice && <p className="chat-notice" role="status">{notice}</p>}
      {error && !active && !newItem && <p className="form-error" role="alert">{error}</p>}
      <div ref={layoutRef} style={{ height: layoutHeight }} className={`chat-layout ${activeId || newItem ? "chat-active" : ""}`}>
        <div className="chat-list" aria-label="会话列表">
          {conversations.length ? conversations.map((conversation) => (
            <button key={conversation.id} className={`chat-list-item ${activeId === conversation.id ? "active" : ""}`}
              disabled={busy || uploading}
              onClick={() => { setActiveId(conversation.id); setRecentConversation(conversation); setMessages([]); setReviews([]); setReviewsOpen(false); setLoadedOlder(false); setNewItem(null); setDraft(""); setReportMessageId(null); setError(""); setNotice(""); onStarted(); }}>
              <span className="avatar">{conversation.counterpart.nickname[0]}</span>
              <span className="chat-list-text"><strong>{conversation.counterpart.nickname}</strong><small>{conversation.item_title}</small>
                <span>{conversation.last_message ? conversation.last_message.body || "[图片]" : "开始沟通"}</span></span>
              {conversation.unread_count > 0 && <b className="chat-unread">{conversation.unread_count}</b>}
            </button>
          )) : <p className="muted chat-empty-list">还没有消息。打开一件商品，点击“联系卖家”开始。</p>}
        </div>
        <div className="chat-thread">
          {(active || newItem) ? <>
            <div className="chat-thread-head">
              <button type="button" className="chat-back" disabled={busy || uploading} onClick={() => { setActiveId(null); setNewItem(null); onStarted(); }} aria-label="返回会话列表"><ArrowLeft size={18} /></button>
              <div><strong>{active?.counterpart.nickname ?? newItem?.seller.nickname}</strong></div>
              {active && <button type="button" className="text-button" disabled={busy} onClick={() => void toggleBlock()}>
                <ShieldOff size={15} />{active.blocked_by_me ? "解除拉黑" : "拉黑"}
              </button>}
              {canDeleteConversation && <button type="button" className="icon-button chat-delete" disabled={busy}
                title="从列表移除会话" aria-label="从列表移除会话" onClick={() => void deleteConversation()}>
                <Trash2 size={16} />
              </button>}
            </div>
            <button type="button" className="chat-item-summary" onClick={() => onOpenItem(active?.item_id ?? newItem!.id)}
              aria-label={`查看商品：${active?.item_title ?? newItem?.title}`}>
              <ProductArt item={newItem ?? { title: active!.item_title, images: active!.item_image ? [active!.item_image] : [], art: "" }} />
              <span><strong>{active?.item_title ?? newItem?.title}</strong>
                <small>{statusText[active?.item_status ?? newItem?.status ?? ""] ?? "状态未知"} · 查看商品详情</small></span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            {active && <div className="chat-deal-actions">
              {active.deal_status === "REQUESTED" && <span>买家已提出预订，等待卖家确认</span>}
              {active.deal_status === "RESERVED" && <span>卖家已确认预订，等待交接</span>}
              {active.deal_status === "SOLD" && <span>卖家已标记售出，等待买家确认</span>}
              {active.deal_status === "CONFIRMED" && <span>双方已确认成交</span>}
              {active.deal_status === "DECLINED" && <span>卖家已拒绝预订</span>}
              {active.deal_status === "CANCELED" && <span>预订已取消</span>}
              {user.id === active.buyer_id && ["NONE", "DECLINED", "CANCELED"].includes(active.deal_status) && active.item_status === "ACTIVE" &&
                <button className="text-button" disabled={busy || active.blocked} onClick={() => void changeDeal("request")}>申请预订</button>}
              {user.id === active.seller_id && active.deal_status === "REQUESTED" && <>
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("reserve")}>确认预订</button>
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("decline")}>拒绝预订</button></>}
              {user.id === active.buyer_id && ["REQUESTED", "RESERVED"].includes(active.deal_status) &&
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("cancel")}>取消预订</button>}
              {user.id === active.seller_id && active.deal_status === "RESERVED" && <>
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("sold")}>确认售出</button>
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("cancel")}>取消预订</button></>}
              {user.id === active.buyer_id && active.deal_status === "SOLD" &&
                <button className="text-button" disabled={busy} onClick={() => void changeDeal("confirm")}>确认已收到</button>}
            </div>}
            {active?.deal_status === "CONFIRMED" && <div className="trade-review-bar">
              <span className="trade-review-bar-title">交易已完成</span>
              {myReview
                ? <span className="trade-review-chip">我的评价 <Stars value={myReview.rating} size={12} /> {myReview.rating} 星</span>
                : <button type="button" className="text-button" disabled={busy}
                    onClick={() => setReviewsOpen(true)}>评价对方</button>}
              {counterpartReview && <span className="trade-review-chip">对方评价 <Stars value={counterpartReview.rating} size={12} /> {counterpartReview.rating} 星</span>}
              <button type="button" className="text-button trade-review-open" onClick={() => setReviewsOpen(true)}>查看评价</button>
            </div>}
            {active?.blocked && <p className="hint">双方已停止联系。聊天记录仍可查看，不能发送新消息。</p>}
            <div className="chat-history" aria-live="polite">
              {hasMore && <button className="text-button" onClick={() => void loadOlder()}>加载更早的消息</button>}
              {messages.map((message) => <div key={message.id} className={`chat-bubble ${message.sender_id === user.id ? "own" : ""}`}>
                {message.body && <p>{message.body}</p>}
                {message.images.length > 0 && <div className="chat-images">{message.images.map((url) =>
                  <button key={url} type="button" className="chat-image-button" aria-label="查看聊天图片" onClick={() => setImageView(url)}>
                    <img src={url} alt="聊天图片" loading="lazy" />
                  </button>)}</div>}
                <time>{new Date(message.created_at).toLocaleString("zh-CN")}</time>
                {message.sender_id !== user.id && !message.hidden && <button className="text-button" type="button"
                  onClick={() => { setReportMessageId(message.id); setReportReason(""); }}><Flag size={13} />举报消息</button>}
              </div>)}
              <div ref={bottom} />
            </div>
            {reportMessageId && <form className="chat-report-form" onSubmit={(event) => void submitReport(event)}>
              <label>举报原因<input required minLength={5} maxLength={1000} value={reportReason}
                onChange={(event) => setReportReason(event.target.value)} placeholder="请说明这条消息的问题" /></label>
              <button className="button secondary" disabled={busy}>提交举报</button>
              <button type="button" className="text-button" onClick={() => setReportMessageId(null)}>取消</button>
            </form>}
            <form className="chat-compose" onSubmit={(event) => void send(event)}>
              <div className="chat-compose-tools">
                <label className={`text-button chat-image-upload ${active?.blocked || busy || uploading || images.length >= 3 ? "disabled" : ""}`}>
                  <ImagePlus size={17} />{uploading ? "上传中…" : "添加图片"}
                  <input type="file" className="sr-only" accept="image/jpeg,image/png,image/webp" multiple
                    aria-label="添加聊天图片" disabled={busy || uploading || active?.blocked || images.length >= 3}
                    onChange={(event) => { void uploadImages(event.target.files); event.target.value = ""; }} />
                </label>
                <span>最多 3 张，每张不超过 6 MB</span>
              </div>
              {newItem && (
                <button
                  type="button"
                  className="text-button chat-draft-tool"
                  disabled={busy}
                  onClick={() => void generateDraft()}
                >
                  <Sparkles size={15} />
                  咨询草稿
                </button>
              )}
              <label className="sr-only" htmlFor="chat-message">消息内容</label>
              <textarea id="chat-message" value={draft} maxLength={2000} rows={2} disabled={busy || active?.blocked}
                placeholder="输入消息，也可以直接发送图片…" onChange={(event) => setDraft(event.target.value)} />
              {images.length > 0 && <div className="chat-attachment-preview">{images.map((url) =>
                <div className="upload-preview" key={url}><img src={url} alt="待发送图片" />
                  <button type="button" disabled={busy || uploading} aria-label="移除待发送图片" onClick={() => setImages((current) => current.filter((image) => image !== url))}><X size={14} /></button>
                </div>)}</div>}
              <div><span>请勿提前转账；交接前当面核实商品。</span>
                <button className="button primary" disabled={busy || uploading || active?.blocked || (!draft.trim() && !images.length)}><Send size={15} />确认发送</button></div>
              {error && <p className="form-error" role="alert">{error}</p>}
            </form>
          </> : <Empty title="选择一条会话" text="你与其他同学的商品沟通会显示在这里。" />}
        </div>
      </div>
      {reviewsOpen && active?.deal_status === "CONFIRMED" && <Modal title="交易评价" onClose={() => setReviewsOpen(false)}>
        <div className="trade-review-dialog">
          {myReview ? <section className="trade-review-block">
            <div className="trade-review-block-head"><strong>我的评价</strong><Stars value={myReview.rating} /><span>{myReview.rating} 星</span></div>
            {myReview.tags.length > 0 && <div className="trade-review-tags">{myReview.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
            {myReview.body && <p>{myReview.body}</p>}
          </section> : <form className="trade-review-form" onSubmit={(event) => void submitReview(event)}>
            <div className="trade-review-form-rating">
              <span>给这次交易打分</span>
              <Stars value={reviewRating} onChange={setReviewRating} size={24} />
              <strong>{reviewRating} 星</strong>
            </div>
            <div className="trade-review-tags">
              {REVIEW_TAGS.map((tag) => <button type="button" key={tag}
                className={reviewTags.includes(tag) ? "active" : ""} aria-pressed={reviewTags.includes(tag)}
                onClick={() => toggleReviewTag(tag)}>{tag}</button>)}
            </div>
            <label className="sr-only" htmlFor="trade-review-body">补充评价</label>
            <textarea id="trade-review-body" rows={3} maxLength={500} value={reviewBody}
              placeholder="补充一句评价（可选，最多 500 字）" onChange={(event) => setReviewBody(event.target.value)} />
            <div className="trade-review-form-actions">
              <span>评价提交后不能修改</span>
              <button className="button primary" disabled={reviewBusy || busy}>{reviewBusy ? "提交中…" : "提交评价"}</button>
            </div>
          </form>}
          {counterpartReview ? <section className="trade-review-block">
            <div className="trade-review-block-head"><strong>对方的评价</strong><Stars value={counterpartReview.rating} /><span>{counterpartReview.rating} 星</span></div>
            {counterpartReview.tags.length > 0 && <div className="trade-review-tags">{counterpartReview.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
            {counterpartReview.body && <p>{counterpartReview.body}</p>}
          </section> : <p className="hint">对方还没有评价；对方提交后会显示在这里。</p>}
        </div>
      </Modal>}
      {imageView && <Modal title="聊天图片" onClose={() => setImageView(null)}><img className="chat-image-full" src={imageView} alt="聊天图片原图" /></Modal>}
    </section>
  );
}
