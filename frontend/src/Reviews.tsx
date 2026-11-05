import { useEffect, useState } from "react";
import { Star } from "lucide-react";
import { api, type TradeReview, type UserReviews } from "./api";

export const REVIEW_TAGS = ["描述相符", "沟通顺畅", "准时守约", "包装仔细", "态度友好"] as const;

export function Stars({ value, onChange, size = 16 }: {
  value: number;
  onChange?: (value: number) => void;
  size?: number;
}) {
  if (onChange) {
    return <span className="trade-stars interactive" role="group" aria-label="选择评分">
      {[1, 2, 3, 4, 5].map((star) => (
        <button type="button" key={star} className={star <= value ? "on" : ""}
          aria-label={`${star} 星`} aria-pressed={star === value} onClick={() => onChange(star)}>
          <Star size={size} fill={star <= value ? "currentColor" : "none"} strokeWidth={1.6} />
        </button>
      ))}
    </span>;
  }
  return <span className="trade-stars" role="img" aria-label={`${value} 星`}>
    {[1, 2, 3, 4, 5].map((star) => (
      <Star key={star} size={size} aria-hidden="true" strokeWidth={1.6}
        fill={star <= value ? "currentColor" : "none"} />
    ))}
  </span>;
}

export function useUserReviews(userId?: string | null, limit = 20) {
  const [data, setData] = useState<UserReviews | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!userId) { setData(null); setError(""); return; }
    let alive = true;
    setData(null);
    setError("");
    void api<UserReviews>(`/users/${encodeURIComponent(userId)}/reviews?limit=${limit}`)
      .then((result) => { if (alive) setData(result); })
      .catch((cause) => { if (alive) setError((cause as Error).message); });
    return () => { alive = false; };
  }, [userId, limit]);
  return { data, error };
}

export function SellerRating({ userId, onOpen }: { userId: string; onOpen?: () => void }) {
  const { data } = useUserReviews(userId, 1);
  const summary = data?.summary;
  const count = summary?.count ?? 0;
  const content = <>
    <Stars value={Math.round(summary?.average ?? 0)} size={13} />
    <strong>{summary?.average !== null && summary?.average !== undefined ? summary.average.toFixed(1) : "—"}</strong>
    <span>{count > 0 ? `${count} 条评价` : "暂无评价"}</span>
    {onOpen && count > 0 && <em>查看</em>}
  </>;
  if (onOpen && count > 0) {
    return <button type="button" className="seller-rating" onClick={onOpen}
      aria-label={`查看 ${count} 条交易评价`}>{content}</button>;
  }
  return <span className="seller-rating static" aria-label={count > 0 ? `${summary?.average} 分，${count} 条评价` : "暂无评价"}>
    {content}
  </span>;
}

function ReviewCard({ review }: { review: TradeReview }) {
  const nickname = review.reviewer?.nickname ?? "匿名同学";
  return <article className="trade-review-card">
    <header>
      <span className="avatar">{nickname[0]}</span>
      <div>
        <strong>{nickname}</strong>
        <small>{new Date(review.created_at).toLocaleDateString("zh-CN")} · {review.item_title}</small>
      </div>
      <Stars value={review.rating} size={14} />
    </header>
    {review.tags.length > 0 && <div className="trade-review-tags">
      {review.tags.map((tag) => <span key={tag}>{tag}</span>)}
    </div>}
    {review.body && <p>{review.body}</p>}
  </article>;
}

export function UserReviewsPanel({ userId }: { userId: string }) {
  const { data, error } = useUserReviews(userId, 30);
  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!data) return <p className="hint">正在加载评价…</p>;
  const { summary, reviews } = data;
  if (!summary.count) {
    return <div className="trade-review-empty">
      <Stars value={0} size={22} />
      <p>还没有收到评价。双方确认成交后，可以互相评价。</p>
    </div>;
  }
  const average = summary.average ?? 0;
  return <>
    <div className="trade-review-overview">
      <div className="trade-review-score">
        <strong>{average.toFixed(1)}</strong>
        <Stars value={Math.round(average)} size={17} />
        <span>{summary.count} 条交易评价</span>
      </div>
      <div className="trade-review-distribution" aria-label="评分分布">
        {summary.distribution.map((entry) => (
          <div key={entry.rating}>
            <span>{entry.rating} 星</span>
            <span className="trade-review-meter"><i style={{ width: `${(entry.count / summary.count) * 100}%` }} /></span>
            <em>{entry.count}</em>
          </div>
        ))}
      </div>
    </div>
    <div className="trade-review-list">
      {reviews.map((review) => <ReviewCard key={review.id} review={review} />)}
    </div>
  </>;
}
