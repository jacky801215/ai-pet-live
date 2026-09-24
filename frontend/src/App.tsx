/**
 * App —— Phase 1 单窗口外壳（UB-3 / FCM-2 / FD-1 / RV-1 / RS-1..RS-5 / RF-1..RF-5）。
 *
 * 页面 runtime 状态（RS-1）：唯一来源 usePetRuntime() 的 loading / error；
 * 组合优先级固定 **error ↓ loading ↓ ready**（RS-2/RS-3/RS-4）：
 * - error：整页错误区，完整保留 status / code / message（鸭子类型读取，不 import API 层）；
 * - loading：统一页面加载区（无 skeleton / 动画 / timer）；
 * - ready：工具条（人工刷新按钮，RF-2）+ 事件模拟器（ES-1，经 onTrigger 注入编排）+ 既有三组件布局；
 *   数据为空时由组件自身的空态表达（empty，RS-4）。
 * 数据流不变：API 层 → store → 组件；App 不取数据、不写 setter、不放定时器、无本地 state（RF-3）。
 * controller prop 仅测试注入用（与 hook 的 RV 注入缝隙同构），生产零参渲染。
 *
 * **Phase 3.2-B（MPF-4 / MPF-5，受权增量）**：新增宠物上下文 —
 * `usePetContext()` 取当前宠物与切换函数，当前宠物传给 `useRuntimePush(selectedPetId)`
 * （切换即重建 push 连接，MPF-4），选择器 `PetSelector` 经 `onSelect` 注入切换函数。
 * App **仍**保持：零 `useState`、零 API import、零 store setter、零 fetch。
 *
 * **§7.1 收口（受权增量）**：由 `usePetContext()` 已返回的 `availablePets` 计算
 * 「当前宠物是否素材待接入」，经 `PetStage` 的 `placeholder` prop 下传
 * （**不新增 import**、**不新增 state**；PetStage 仍不消费 store、PetPlayer 仍不 import 目录）。
 *
 * **CR-4（受权增量，FCM-2 v1.1）**：新增 AI 生成内容标识 `AiContentLabel`（合规要求），
 * **仅 ready 态**渲染（error / loading 无直播画面，故不渲染）。该组件为纯静态展示，
 * App 仍保持：零 `useState`、零 API import、零 store setter、零 fetch、零定时器（RF-3）。
 *
 * **CR-5（受权增量，FCM-4 v1.2）**：为标识落地**独立样式表**
 * （`src/styles/ai-content-label.css`，由 `src/main.tsx` 引入；组件侧**零改动**）。
 * 仅新增一个**定位容器** `div.live-stage`（同时包裹标识与 `PetStage`），
 * 使标识以 `absolute` 锚定**画面右上角**（原本标识与画面是兄弟节点、无定位上下文）。
 * App **仍**保持：零 `useState`、零 API import、零 store setter、零 fetch、零定时器，
 * 且**未新增任何 import**（故两处 App import 白名单守卫无需改动）。
 */
import AiContentLabel from "./components/AiContentLabel";
import EventList from "./components/EventList";
import EventSimulator from "./components/EventSimulator";
import PetSelector from "./components/PetSelector";
import PetStage from "./components/PetStage";
import StatusBar from "./components/StatusBar";
import { usePetContext } from "./hooks/usePetContext";
import { usePetRuntime, type PetRuntimeController } from "./hooks/usePetRuntime";
import { useRuntimePush } from "./hooks/useRuntimePush";

export default function App({
  controller,
}: {
  /** 仅测试注入用：生产零参。 */
  controller?: PetRuntimeController;
}) {
  // 接收完整 runtime；数据切片（playback/recentEvents/stats）由子组件经 store 消费（FCM-3/RS-4），
  // 页面级状态只消费 loading / error（RS-1）；triggerEvent 为模拟器编排（ES-2）
  const runtime = usePetRuntime({ controller });
  const { loading, error, triggerEvent } = runtime;

  // MPF-4 / MPF-5：宠物上下文。当前宠物来自 store（经 hook），切换函数注入选择器。
  const { selectedPetId, availablePets, selectPet } = usePetContext();

  // §7.1 收口：当前宠物是否「素材待接入」（目录由 hook 提供，故无需新增 import）。
  // 判定只在此处做一次，经 prop 下传；PetStage 保持零 store 消费，PetPlayer 保持不读目录。
  const selectedIsPlaceholder =
    availablePets.find((pet) => pet.pet_id === selectedPetId)?.placeholder === true;

  // PC-1 + MPF-4：push channel 生命周期（mount → connect；cleanup → close）。
  // 被动更新通道：不触发 refresh、不拉取数据（PC-3）；写入一律经 store（PC-4/PC-5）。
  // petId 变化 ⇒ 旧连接 close + 新上下文连接 connect（用户主动切换，非自动重连）。
  useRuntimePush(selectedPetId);

  if (error !== null) {
    // RS-3：status / code / message 原样展示；鸭子类型读取以维持 App 的 import 白名单
    const detail = error as Error & { status?: unknown; code?: unknown };
    return (
      <div className="app-shell" data-phase="runtime-error" data-testid="app-error">
        <p className="app-error__title">互动服务出错</p>
        <p className="app-error__status" data-testid="app-error-status">
          {String(detail.status ?? "—")}
        </p>
        <p className="app-error__code" data-testid="app-error-code">
          {String(detail.code ?? "—")}
        </p>
        <p className="app-error__message" data-testid="app-error-message">
          {detail.message}
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="app-shell" data-phase="runtime-loading" data-testid="app-loading">
        <p className="app-loading__text">加载中…</p>
      </div>
    );
  }

  return (
    <div className="app-shell" data-phase="components">
      <div className="app-toolbar" data-testid="app-toolbar">
        <button
          type="button"
          className="app-toolbar__refresh"
          data-testid="app-refresh"
          onClick={() => {
            // RF-2：manual caller → hook → API → store；失败原样进入 error（RF-4）。
            // void 丢弃的是 Promise 对象本身，错误已由 controller 写入 error，无未处理 rejection。
            void runtime.refresh();
          }}
        >
          刷新
        </button>
        <PetSelector availablePets={availablePets} onSelect={selectPet} />
      </div>
      <EventSimulator
        disabled={loading}
        onTrigger={(eventType) => {
          // ES-2：click → triggerEvent（hook 编排）→ simulateEvent → loadRuntimeData 回读写 store；
          // 失败 error 原样进通道（ES-4，与 RF-4 同口径）；void 语义与 refresh 相同。
          void triggerEvent(eventType);
        }}
      />
      {/* CR-5：定位容器 —— 标识与画面同容器，使标识锚定「画面右上角」（FCM-4 v1.2） */}
      <div className="live-stage">
        {/* CR-4：AI 生成内容标识 —— 直播间画面右上角，ready 态全程可见 */}
        <AiContentLabel />
        <PetStage placeholder={selectedIsPlaceholder} />
      </div>
      <StatusBar />
      <EventList />
    </div>
  );
}
