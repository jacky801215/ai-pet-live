/**
 * StatusBar —— 统计展示（FCM-2，FCM-3）。
 *
 * 只消费 store 的 `stats`；展示 `events` / `actions` / `total`（API-4）。
 * 分布字段为计数表（Record<string, number>），以紧凑文本形式呈现。
 */
import { usePetStore } from "../stores/usePetStore";

/** 把计数表渲染为 "gift:5 like:2" 形式的文本（空表展示占位符）。 */
function formatCounts(counts: Record<string, number>): string {
  const keys = Object.keys(counts);
  if (keys.length === 0) {
    return "—";
  }
  return keys.map((key) => `${key}:${String(counts[key])}`).join(" ");
}

export default function StatusBar() {
  const stats = usePetStore((s) => s.stats);

  if (stats === null) {
    return (
      <footer className="status-bar status-bar--empty" data-testid="status-bar-empty">
        暂无统计数据
      </footer>
    );
  }

  return (
    <footer className="status-bar" data-testid="status-bar">
      <span className="status-bar__total" data-testid="status-bar-total">
        互动总数 {String(stats.total)}
      </span>
      <span className="status-bar__events" data-testid="status-bar-events">
        事件分布 {formatCounts(stats.events)}
      </span>
      <span className="status-bar__actions" data-testid="status-bar-actions">
        动作分布 {formatCounts(stats.actions)}
      </span>
    </footer>
  );
}
