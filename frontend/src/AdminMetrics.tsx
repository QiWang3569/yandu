import React, { useState } from 'react';
import {
  Users,
  UserPlus,
  Eye,
  AlertCircle,
  TrendingUp,
  Sparkles,
  ShoppingBag,
  Zap,
  MessageSquare,
  Clock,
  ArrowRightLeft,
  FileEdit,
  Skull,
  Timer,
  Activity,
  Coins,
  Banknote,
  Layers,
  ArrowUpRight,
  Filter,
} from 'lucide-react';

interface GrowthTrend {
  date: string;
  new_users: number;
  cumulative_users: number;
}

interface UserGrowthData {
  total_users: number;
  base_count: number;
  trend: GrowthTrend[];
}

interface FunnelStage {
  stage: string;
  count: number;
  pct: number;
}

interface VisitorFunnelData {
  total_unique_visitors: number;
  unregistered_browsers: number;
  funnel: FunnelStage[];
  friction_drop_off_pct: number;
}

export interface CategoryStat {
  category: string;
  total: number;
  sold: number;
  rate_pct: number;
  gmv_yuan?: number;
  total_7d?: number;
  sold_7d?: number;
  rate_7d_pct?: number;
}

export interface ZombieItem {
  id: string;
  title: string;
  price_cents: number;
  category: string;
  days_listed: number;
}

export interface PageDwellStat {
  page: string;
  views: number;
  avg_seconds: number;
  total_seconds: number;
}

export interface HesitationItem {
  id: string;
  title: string;
  price_cents: number;
  category: string;
  total_dwell_seconds: number;
  avg_dwell_seconds: number;
  view_count: number;
  diagnosis: string;
}

export interface BusinessOverviewData {
  realtime?: {
    active_online_users: number;
    active_sessions: number;
    rolling_anon_uv: number;
    total_online_presence: number;
  };
  liquidity: {
    total_items: number;
    sold_items: number;
    sell_through_rate_pct: number;
    avg_days_to_sell: number | null;
    total_gmv_yuan?: number;
    avg_order_value_yuan?: number;
    recent_30d_gmv_yuan?: number;
    active_items: number;
    active_demands: number;
    supply_demand_ratio: number;
    categories: CategoryStat[];
    first_inquiry_rate_72h_pct?: number;
    avg_hours_to_first_inquiry?: number;
    zombie_items_count?: number;
    zombie_rate_pct?: number;
    top_zombies?: ZombieItem[];
  };
  dwell_insights?: {
    page_distribution: PageDwellStat[];
    hesitation_items: HesitationItem[];
  };
  ai_attribution: {
    total_notifications: number;
    chat_conversions: number;
    push_to_chat_cvr_pct: number;
    attributed_deals: number;
    agent_attributed_deal_rate_pct: number;
  };
  friction: {
    total_drafts: number;
    total_published: number;
    draft_abandonment_pct: number;
    total_conversations: number;
    responded_conversations_pct: number;
  };
}

type TabKey = 'all' | 'liquidity' | 'users' | 'items' | 'ai';

export function AdminMetrics({
  growthData,
  funnelData,
  businessData,
  error,
}: {
  growthData: UserGrowthData | null;
  funnelData: VisitorFunnelData | null;
  businessData: BusinessOverviewData | null;
  error?: string | null;
}) {
  const [activeTab, setActiveTab] = useState<TabKey>('all');

  if (error) {
    return <p className="form-error">加载指标数据失败：{error}</p>;
  }

  const trend = growthData?.trend ?? [];
  const width = 640;
  const height = 220;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 35;

  const maxVal = Math.max(...trend.map((d) => d.cumulative_users), 10);
  const minVal = Math.min(...trend.map((d) => d.cumulative_users), 0);

  const getX = (idx: number) =>
    padLeft + (idx / Math.max(trend.length - 1, 1)) * (width - padLeft - padRight);
  const getY = (val: number) =>
    height - padBottom - ((val - minVal) / Math.max(maxVal - minVal, 1)) * (height - padTop - padBottom);

  const linePoints = trend.map((d, i) => `${getX(i)},${getY(d.cumulative_users)}`).join(' ');
  const areaPoints = trend.length
    ? `${getX(0)},${height - padBottom} ${linePoints} ${getX(trend.length - 1)},${height - padBottom}`
    : '';

  const total30dNew = trend.reduce((sum, d) => sum + d.new_users, 0);

  const liq = businessData?.liquidity;
  const ai = businessData?.ai_attribution;
  const fric = businessData?.friction;
  const dwell = businessData?.dwell_insights;

  const formatPageName = (p: string) => {
    switch (p) {
      case 'market':
        return '逛逛校园瀑布流';
      case 'item_detail':
        return '商品详情页';
      case 'wanted':
        return '求购需求看板';
      case 'publish':
        return '发布商品页面';
      case 'messages':
      case 'chat':
        return '私聊沟通会话';
      case 'intents':
        return 'AI 代蹲任务中心';
      case 'profile':
        return '个人主页';
      default:
        return p;
    }
  };

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'all', label: '全部数据总览', icon: <Layers size={15} /> },
    { key: 'liquidity', label: '交易与流动性', icon: <Banknote size={15} /> },
    { key: 'users', label: '用户与访客漏斗', icon: <Users size={15} /> },
    { key: 'items', label: '商品健康与注意力', icon: <ShoppingBag size={15} /> },
    { key: 'ai', label: 'AI 撮合与体验摩擦', icon: <Sparkles size={15} /> },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
      {/* 顶部模组切换 Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          paddingBottom: '4px',
          borderBottom: '1px solid #e2e8e1',
        }}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 14px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                border: 'none',
                cursor: 'pointer',
                backgroundColor: isActive ? '#35533a' : '#f0f4f0',
                color: isActive ? '#ffffff' : '#4d6150',
                transition: 'all 0.15s ease',
                whiteSpace: 'nowrap',
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ========================================================
          分类一：💰 交易与市场流动性 (Transaction & Liquidity)
         ======================================================== */}
      {(activeTab === 'all' || activeTab === 'liquidity') && (
        <section style={sectionContainerStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ padding: '6px', backgroundColor: '#fcf6ed', borderRadius: '8px', color: '#b87d3b' }}>
                <Banknote size={20} />
              </div>
              <div>
                <h3 style={sectionTitleStyle}>1. 交易金额与市场流动性 (Transaction & Liquidity)</h3>
                <span style={sectionSubStyle}>追踪全站成交流水、挂牌去化速度与各品类吸金能力</span>
              </div>
            </div>
            <span style={badgeStyle}>核心商业指标</span>
          </div>

          {/* 交易 KPI 指标小卡列 */}
          <div style={kpiGridStyle}>
            <div style={{ ...cardStyle, borderLeft: '3px solid #b87d3b' }}>
              <span style={cardLabelStyle}>全站成交总额 (GMV)</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#8c5318' }}>
                ¥{(liq?.total_gmv_yuan ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <span style={cardSubStyle}>
                近 30 天成交 ¥{(liq?.recent_30d_gmv_yuan ?? 0).toLocaleString()}
              </span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>平均成交客单价 (AOV)</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#253d29' }}>
                ¥{liq?.avg_order_value_yuan ?? 0}
              </div>
              <span style={cardSubStyle}>每单成交平均金额</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>全站挂牌售出率 (STR)</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#1b5e20' }}>
                {liq?.sell_through_rate_pct ?? 0}%
              </div>
              <span style={cardSubStyle}>
                已售 {liq?.sold_items ?? 0} / 挂单 {liq?.total_items ?? 0} 件
              </span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>平均成交周期</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#2b5e7d' }}>
                {liq?.avg_days_to_sell == null ? "暂无成交样本" : `${liq.avg_days_to_sell} 天`}
              </div>
              <span style={cardSubStyle}>从发布到买家确认</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>市场供求比 (供/求)</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#354d3d' }}>
                {liq?.supply_demand_ratio ?? 0}
              </div>
              <span style={cardSubStyle}>
                在售 {liq?.active_items ?? 0} 件 : 求购 {liq?.active_demands ?? 0} 条
              </span>
            </div>
          </div>

          {/* 各品类去化与成交金额排行看板 */}
          <div style={panelStyle}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#253d29', marginBottom: '14px' }}>
              各品类去化速度与成交金额排行 (Sell-Through & GMV by Category)
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {liq?.categories.map((c) => (
                <div key={c.category} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: '#253d29', fontWeight: 600 }}>{c.category}</span>
                    <span style={{ color: '#556858' }}>
                      成交额: <strong style={{ color: '#8c5318' }}>¥{(c.gmv_yuan ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}</strong> · 近 7 天动销: <strong>{c.rate_7d_pct ?? 0}%</strong> (售 {c.sold_7d ?? 0}/新 {c.total_7d ?? 0}) · 全周期去化: <strong>{c.rate_pct}%</strong>
                    </span>
                  </div>
                  <div style={barBgStyle}>
                    <div
                      style={{
                        height: '100%',
                        width: `${Math.max(c.rate_pct, 2)}%`,
                        backgroundColor: c.rate_pct >= 40 ? '#2e7d32' : c.rate_pct >= 20 ? '#4caf50' : '#8bc34a',
                        borderRadius: '5px',
                        transition: 'width 0.4s ease',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ========================================================
          分类二：👥 用户增长与访客全链路 (Users & Funnel)
         ======================================================== */}
      {(activeTab === 'all' || activeTab === 'users') && (
        <section style={sectionContainerStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ padding: '6px', backgroundColor: '#eef5ef', borderRadius: '8px', color: '#2e7d32' }}>
                <Users size={20} />
              </div>
              <div>
                <h3 style={sectionTitleStyle}>2. 用户规模与访客转化漏斗 (Users & Visitor Funnel)</h3>
                <span style={sectionSubStyle}>监控实时在线驻留、注册走势与免登录访客拦截流失</span>
              </div>
            </div>
            <span style={{ ...badgeStyle, backgroundColor: '#eaf4eb', color: '#235e29' }}>流量与留存</span>
          </div>

          {/* 用户与访客 KPI 指标小卡列 */}
          <div style={kpiGridStyle}>
            <div style={{ ...cardStyle, borderLeft: '3px solid #2e7d32' }}>
              <span style={cardLabelStyle}>当前实时在线</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#1b5e20' }}>
                {businessData?.realtime?.total_online_presence ?? 1} 人
              </div>
              <span style={cardSubStyle}>
                已登录 {businessData?.realtime?.active_online_users ?? 1} · 访客 {businessData?.realtime?.rolling_anon_uv ?? 0}
              </span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>累计注册用户</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#253d29' }}>
                {growthData?.total_users ?? 0} 人
              </div>
              <span style={cardSubStyle}>近 30 天新增 +{total30dNew}</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>7 天独立访客 (UV)</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#1f4861' }}>
                {funnelData?.total_unique_visitors ?? 0}
              </div>
              <span style={cardSubStyle}>独立设备浏览器指纹</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>纯浏览未注册人数</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#7a5118' }}>
                {funnelData?.unregistered_browsers ?? 0}
              </div>
              <span style={cardSubStyle}>仅逛街未建立账号</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>登录拦截跳出率</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#8c2e2e' }}>
                {funnelData?.friction_drop_off_pct ?? 0}%
              </div>
              <span style={cardSubStyle}>拦截后放弃注册比例</span>
            </div>
          </div>

          {/* 图表双栏：左侧注册增长折线图，右侧流失漏斗 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>
            {/* 注册人数累计成长折线图 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    注册用户增长走势图 (最近 30 天)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>累计注册用户曲线与每日新增走势</span>
                </div>
                <TrendingUp size={18} color="#35533a" />
              </div>

              {trend.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: '#94a092' }}>暂无足够注册时间数据</div>
              ) : (
                <div style={{ width: '100%', overflowX: 'auto' }}>
                  <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', minWidth: '320px' }}>
                    <defs>
                      <linearGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#3b6e47" stopOpacity="0.28" />
                        <stop offset="100%" stopColor="#3b6e47" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>

                    {[0, 0.5, 1].map((ratio) => {
                      const y = height - padBottom - ratio * (height - padTop - padBottom);
                      const val = Math.round(minVal + ratio * (maxVal - minVal));
                      return (
                        <g key={ratio}>
                          <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="#e4eae3" strokeDasharray="3 3" />
                          <text x={padLeft - 8} y={y + 3} textAnchor="end" fontSize="10" fill="#94a092">
                            {val}
                          </text>
                        </g>
                      );
                    })}

                    {areaPoints && <polygon points={areaPoints} fill="url(#growthGrad)" />}
                    {linePoints && <polyline fill="none" stroke="#3b6e47" strokeWidth="2.5" points={linePoints} />}

                    {trend.map((d, i) => (
                      <g key={d.date} className="growth-point">
                        <circle
                          cx={getX(i)}
                          cy={getY(d.cumulative_users)}
                          r="3.5"
                          fill="#2e5938"
                          stroke="#ffffff"
                          strokeWidth="1.5"
                          style={{ cursor: 'pointer' }}
                        >
                          <title>{`${d.date}: 累计 ${d.cumulative_users} 人 (当日 +${d.new_users})`}</title>
                        </circle>
                      </g>
                    ))}

                    <text x={padLeft} y={height - 10} fontSize="11" fill="#889889">
                      {trend[0]?.date}
                    </text>
                    <text x={width - padRight} y={height - 10} textAnchor="end" fontSize="11" fill="#889889">
                      {trend[trend.length - 1]?.date}
                    </text>
                  </svg>
                </div>
              )}
            </div>

            {/* 访客流失与转化漏斗 */}
            <div style={panelStyle}>
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                  访客全链路转化与流失漏斗 (最近 7 天)
                </h4>
                <span style={{ fontSize: '11px', color: '#889889' }}>
                  从未登录纯浏览，到触发意向拦截、索取验证码，至最终注册
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {funnelData?.funnel.map((f, i) => (
                  <div key={f.stage} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                      <span style={{ fontWeight: 500, color: '#354d3d' }}>{f.stage}</span>
                      <span style={{ color: '#687b6b' }}>
                        <strong>{f.count}</strong> 人 ({f.pct}%)
                      </span>
                    </div>
                    <div
                      style={{
                        height: '14px',
                        backgroundColor: '#edf2ed',
                        borderRadius: '7px',
                        overflow: 'hidden',
                        width: '100%',
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${Math.max(f.pct, 3)}%`,
                          backgroundColor: ['#3b6e47', '#50895e', '#b87d3b', '#2b7899'][i % 4],
                          borderRadius: '7px',
                          transition: 'width 0.4s ease',
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ========================================================
          分类三：📦 商品健康度与用户注意力 (Item Health & Attention)
         ======================================================== */}
      {(activeTab === 'all' || activeTab === 'items') && (
        <section style={sectionContainerStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ padding: '6px', backgroundColor: '#eef2f5', borderRadius: '8px', color: '#2b5e7d' }}>
                <ShoppingBag size={20} />
              </div>
              <div>
                <h3 style={sectionTitleStyle}>3. 商品健康度与注意力分析 (Item Health & Attention)</h3>
                <span style={sectionSubStyle}>评估卖家反馈时效、死库存清退、页面停留时长与犹豫商品</span>
              </div>
            </div>
            <span style={{ ...badgeStyle, backgroundColor: '#ebf2f7', color: '#204a63' }}>货品诊断</span>
          </div>

          {/* 商品健康度 KPI 指标小卡列 */}
          <div style={kpiGridStyle}>
            <div style={{ ...cardStyle, borderLeft: '3px solid #2e7d32' }}>
              <span style={cardLabelStyle}>72h 初次咨询动销率 (P0)</span>
              <div
                style={{
                  fontSize: '24px',
                  fontWeight: 700,
                  color: (liq?.first_inquiry_rate_72h_pct ?? 0) >= 30 ? '#1b5e20' : '#b45309',
                }}
              >
                {liq?.first_inquiry_rate_72h_pct ?? 0}%
              </div>
              <span style={cardSubStyle}>
                健康线 &gt;30% · 首聊均耗时 {liq?.avg_hours_to_first_inquiry ?? 0}h
              </span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>死库存积压率</span>
              <div
                style={{
                  fontSize: '24px',
                  fontWeight: 700,
                  color: (liq?.zombie_rate_pct ?? 0) > 35 ? '#b91c1c' : '#253d29',
                }}
              >
                {liq?.zombie_rate_pct ?? 0}%
              </div>
              <span style={cardSubStyle}>
                在售 &gt;14 天零咨询：{liq?.zombie_items_count ?? 0} 件
              </span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>心动但犹豫商品数</span>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#b45309' }}>
                {dwell?.hesitation_items?.length ?? 0} 件
              </div>
              <span style={cardSubStyle}>高停留浏览但 0 私聊</span>
            </div>

            <div style={cardStyle}>
              <span style={cardLabelStyle}>最高粘性页面</span>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#2b5e7d', marginTop: '6px' }}>
                {dwell?.page_distribution?.[0] ? formatPageName(dwell.page_distribution[0].page) : '市场瀑布流'}
              </div>
              <span style={cardSubStyle}>
                均停 {dwell?.page_distribution?.[0]?.avg_seconds ?? 0} 秒
              </span>
            </div>
          </div>

          {/* 深度商品与注意力卡片行 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {/* 全站停留时长分布 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    全站各页面平均停留时长 (Dwell Time)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>
                    前端 sendBeacon 埋点统计的学生注意力投向
                  </span>
                </div>
                <Clock size={18} color="#2b5e7d" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {dwell?.page_distribution && dwell.page_distribution.length > 0 ? (
                  dwell.page_distribution.map((p) => (
                    <div key={p.page} style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                        <span style={{ color: '#2d3d30', fontWeight: 500 }}>{formatPageName(p.page)}</span>
                        <span style={{ color: '#687b6b' }}>
                          均停 <strong>{p.avg_seconds}s</strong> · {p.views} 次浏览
                        </span>
                      </div>
                      <div style={barBgStyle}>
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.min(Math.max((p.avg_seconds / 60) * 100, 4), 100)}%`,
                            backgroundColor: '#2b7899',
                            borderRadius: '5px',
                            transition: 'width 0.4s ease',
                          }}
                        />
                      </div>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: '12px', color: '#889889', padding: '20px 0', textAlign: 'center' }}>
                    正在累积停留打点数据…
                  </div>
                )}
              </div>
            </div>

            {/* 心动但犹豫商品透视 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    「心动但犹豫」商品透视 (高停留 · 零咨询)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>
                    买家仔细翻看详情但未咨询，高概率为定价偏高或成色细节缺失
                  </span>
                </div>
                <Activity size={18} color="#b87d3b" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {dwell?.hesitation_items && dwell.hesitation_items.length > 0 ? (
                  dwell.hesitation_items.map((h) => (
                    <div
                      key={h.id}
                      style={{
                        backgroundColor: '#fffdf9',
                        border: '1px solid #f2e7d5',
                        borderRadius: '8px',
                        padding: '8px 10px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '12px', fontWeight: 600, color: '#2d3d30' }}>
                          {h.title}
                        </span>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: '#b45309' }}>
                          ¥{(h.price_cents / 100).toFixed(2)}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#8a7251' }}>
                        <span>
                          累计停留 <strong>{h.total_dwell_seconds}s</strong> · {h.view_count} 人详览
                        </span>
                        <span style={{ color: '#c2410c' }}>私聊数：0</span>
                      </div>
                      <div style={{ fontSize: '10px', color: '#846b45', fontStyle: 'italic' }}>
                        💡 {h.diagnosis}
                      </div>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: '12px', color: '#889889', padding: '20px 0', textAlign: 'center' }}>
                    暂无明显「高停留零咨询」的犹豫商品。
                  </div>
                )}
              </div>
            </div>

            {/* 死库存清退清单 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    滞销死库存清退清单 (Zombie Listings)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>
                    在售 &gt; 14 天且咨询为 0，需引导卖家调价或擦亮
                  </span>
                </div>
                <Skull size={18} color="#b91c1c" />
              </div>

              {liq?.top_zombies && liq.top_zombies.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {liq.top_zombies.map((z) => (
                    <div
                      key={z.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '11px',
                        backgroundColor: '#fbfdfa',
                        border: '1px solid #ebeee9',
                        padding: '8px 10px',
                        borderRadius: '6px',
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ color: '#2a3b2c', fontWeight: 600 }}>{z.title}</span>
                        <span style={{ color: '#7a8c7c' }}>{z.category}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#9e3b3b', fontWeight: 600 }}>¥{(z.price_cents / 100).toFixed(0)}</div>
                        <div style={{ color: '#889889', fontSize: '10px' }}>挂单 {z.days_listed} 天</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: '#2e7d32', padding: '20px 0', textAlign: 'center' }}>
                  🎉 目前全站暂无严重积压超过 14 天的零咨询商品。
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ========================================================
          分类四：🤖 AI 智能撮合与交易体验摩擦 (AI & Friction)
         ======================================================== */}
      {(activeTab === 'all' || activeTab === 'ai') && (
        <section style={sectionContainerStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ padding: '6px', backgroundColor: '#fcf3eb', borderRadius: '8px', color: '#b45309' }}>
                <Sparkles size={20} />
              </div>
              <div>
                <h3 style={sectionTitleStyle}>4. AI 智能撮合与沟通体验摩擦 (AI & Friction)</h3>
                <span style={sectionSubStyle}>评估自然语言代蹲助手真实撮合成效与买卖沟通摩擦</span>
              </div>
            </div>
            <span style={{ ...badgeStyle, backgroundColor: '#faece1', color: '#9c4404' }}>技术与体验</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {/* AI 代蹲价值 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    AI 自然语言代蹲撮合价值 (AI Attribution)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>验证语义精筛带来的买卖私聊与成交转化</span>
                </div>
                <Sparkles size={18} color="#b87d3b" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={statRowStyle}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Zap size={16} color="#d97706" />
                    <span style={{ fontSize: '13px', color: '#354d3d' }}>代蹲推送私聊转化率 (CVR)</span>
                  </div>
                  <span style={{ fontSize: '16px', fontWeight: 700, color: '#b45309' }}>
                    {ai?.push_to_chat_cvr_pct ?? 0}%
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: '#8a9b8b', marginTop: '-6px' }}>
                  推送 {ai?.total_notifications ?? 0} 次通知中，促成 {ai?.chat_conversions ?? 0} 次买卖私聊
                </span>

                <div style={statRowStyle}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <ArrowRightLeft size={16} color="#059669" />
                    <span style={{ fontSize: '13px', color: '#354d3d' }}>代蹲成交贡献率 (Attributed Deals)</span>
                  </div>
                  <span style={{ fontSize: '16px', fontWeight: 700, color: '#047857' }}>
                    {ai?.agent_attributed_deal_rate_pct ?? 0}%
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: '#8a9b8b', marginTop: '-6px' }}>
                  全站成交商品中，有 {ai?.attributed_deals ?? 0} 件由代蹲助手率先命中并撮合
                </span>
              </div>
            </div>

            {/* 体验摩擦与防损 */}
            <div style={panelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#253d29' }}>
                    交易摩擦与沟通体验 (Friction & Trust)
                  </h4>
                  <span style={{ fontSize: '11px', color: '#889889' }}>评估发布门槛与买卖双方沟通效率</span>
                </div>
                <FileEdit size={18} color="#2b5e7d" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={statRowStyle}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <AlertCircle size={16} color="#dc2626" />
                    <span style={{ fontSize: '13px', color: '#354d3d' }}>草稿放弃率 (Draft Abandonment)</span>
                  </div>
                  <span style={{ fontSize: '16px', fontWeight: 700, color: '#b91c1c' }}>
                    {fric?.draft_abandonment_pct ?? 0}%
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: '#8a9b8b', marginTop: '-6px' }}>
                  存入 {fric?.total_drafts ?? 0} 件草稿未发布 / 累计挂牌 {fric?.total_published ?? 0} 件
                </span>

                <div style={statRowStyle}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <MessageSquare size={16} color="#0284c7" />
                    <span style={{ fontSize: '13px', color: '#354d3d' }}>卖家私聊有效回复率</span>
                  </div>
                  <span style={{ fontSize: '16px', fontWeight: 700, color: '#0369a1' }}>
                    {fric?.responded_conversations_pct ?? 0}%
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: '#8a9b8b', marginTop: '-6px' }}>
                  总会话 {fric?.total_conversations ?? 0} 个中，买家首次咨询后卖家及时回复的比例
                </span>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

const sectionContainerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '14px',
};

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const sectionTitleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '16px',
  fontWeight: 700,
  color: '#1f3323',
};

const sectionSubStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#7b8c7e',
};

const badgeStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  padding: '4px 8px',
  borderRadius: '6px',
  backgroundColor: '#fbf4ea',
  color: '#8c5318',
};

const kpiGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  gap: '12px',
};

const cardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e5ebe4',
  borderRadius: '10px',
  padding: '14px',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  boxShadow: '0 1px 4px rgba(35, 60, 40, 0.03)',
};

const cardLabelStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#657766',
  fontWeight: 500,
};

const cardSubStyle: React.CSSProperties = {
  fontSize: '11px',
  color: '#889889',
};

const panelStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e5ebe4',
  borderRadius: '12px',
  padding: '18px',
  boxShadow: '0 2px 8px rgba(35, 60, 40, 0.04)',
};

const barBgStyle: React.CSSProperties = {
  height: '10px',
  backgroundColor: '#edf2ed',
  borderRadius: '5px',
  overflow: 'hidden',
  width: '100%',
};

const statRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};
