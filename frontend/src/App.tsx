/**
 * App —— Phase 1 单窗口外壳（UB-3 / FCM-2 / FD-1 / RV-1 / RS-1..RS-5）。
 *
 * 页面 runtime 状态（RS-1）：唯一来源 usePetRuntime() 的 loading / error；
 * 组合优先级固定 **error ↓ loading ↓ ready**（RS-2/RS-3/RS-4）：
 * - error：整页错误区，完整保留 status / code / message（鸭子类型读取，不 import API 层）；
 * - loading：统一页面加载区（无 skeleton / 动画 / timer）；
 * - ready：既有三组件布局；数据为空时由组件自身的空态表达（empty，RS-4）。
 * 数据流不变：API 层 → store → 组件；App 不取数据、不写 setter、不放定时器。
 * controller prop 仅测试注入用（与 hook 的 RV 注入缝隙同构），生产零参渲染。
 */
import EventList from "./components/EventList";
import PetStage from "./components/PetStage";
import StatusBar from "./components/StatusBar";
import { usePetRuntime, type PetRuntimeController } from "./hooks/usePetRuntime";

export default function App({
  controller,
}: {
  /** 仅测试注入用：生产零参。 */
  controller?: PetRuntimeController;
}) {
  // 接收完整 runtime；数据切片（playback/recentEvents/stats）由子组件经 store 消费（FCM-3/RS-4），
  // 页面级状态只消费 loading / error（RS-1）
  const runtime = usePetRuntime({ controller });
  const { loading, error } = runtime;

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
      <PetStage />
      <StatusBar />
      <EventList />
    </div>
  );
}
