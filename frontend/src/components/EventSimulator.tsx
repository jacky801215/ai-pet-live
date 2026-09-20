/**
 * EventSimulator —— 事件模拟器面板（ES-1 ~ ES-4；FCM-2 经 ES 文档局部修订后的第五件组件）。
 *
 * 职责（ES-1）：**只**渲染三个固定按钮（gift / comment / follow）并把点击转交 `onTrigger`。
 * 数据流（ES-2）：click → onTrigger（由 App 注入 hook 层 triggerEvent 编排）→ simulateEvent →
 * 成功回读 loadRuntimeData → store；本组件**零 import**：不 import API（FCM-3 / UB-1）、
 * 不 import store / hook、无 useState / useEffect / ref（ES-4：状态表达全部复用 hook 通道）。
 * 本组件不做任何网络请求、不拼接 URL、不持有状态、不持久化。
 */

/** 模拟器固定事件类型（ES-3：恰三个，禁止自由输入 / payload 编辑器）。 */
export const SIMULATOR_EVENT_TYPES = ["gift", "comment", "follow"] as const;

export type SimulatorEventType = (typeof SIMULATOR_EVENT_TYPES)[number];

interface EventSimulatorProps {
  /** 触发进行中禁用按钮（ES-4 允许的表达细节；复用 hook loading，无第二套状态）。 */
  disabled: boolean;
  /** 点击转交（ES-2：编排归 hook 层；本组件不感知 API / store）。 */
  onTrigger: (eventType: SimulatorEventType) => void;
}

export default function EventSimulator({ disabled, onTrigger }: EventSimulatorProps) {
  return (
    <section className="event-simulator" data-testid="event-simulator">
      {SIMULATOR_EVENT_TYPES.map((eventType) => (
        <button
          key={eventType}
          type="button"
          className={`event-simulator__btn event-simulator__btn--${eventType}`}
          data-testid={`event-simulator-${eventType}`}
          disabled={disabled}
          onClick={() => onTrigger(eventType)}
        >
          {eventType}
        </button>
      ))}
    </section>
  );
}
