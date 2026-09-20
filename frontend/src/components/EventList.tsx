/**
 * EventList —— 最近事件列表（FCM-2，FCM-3）。
 *
 * 只消费 store 的 `recentEvents`（服务端已排序，组件不再排序/裁剪 —— FS-1）；
 * 每项展示 `event_type` / `action_name` / `created_at`（后两者可空，缺省展示占位符）。
 */
import { usePetStore } from "../stores/usePetStore";

export default function EventList() {
  const events = usePetStore((s) => s.recentEvents);

  if (events.length === 0) {
    return (
      <section className="event-list event-list--empty" data-testid="event-list-empty">
        暂无最近事件
      </section>
    );
  }

  return (
    <section className="event-list" data-testid="event-list">
      <ul className="event-list__items">
        {events.map((event) => (
          <li className="event-list__item" key={event.id} data-testid="event-list-item">
            <span className="event-list__type" data-testid="event-item-type">
              {event.event_type}
            </span>
            <span className="event-list__action" data-testid="event-item-action">
              {event.action_name ?? "—"}
            </span>
            <time className="event-list__time" data-testid="event-item-time">
              {event.created_at ?? "—"}
            </time>
          </li>
        ))}
      </ul>
    </section>
  );
}
