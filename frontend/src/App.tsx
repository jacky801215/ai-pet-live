/**
 * App —— Phase 1 单窗口外壳（UB-3 / FCM-2：只做组件组合）。
 *
 * 数据流向：API 层 → Store → 组件（FS-4 / FCM-3）。本组件只组合子组件：
 * 不 import store、不 import API 层、不自取数据、不持状态、不放定时器。
 * 数据获取接线归后续步骤（FCM-5 Deferred）。
 */
import EventList from "./components/EventList";
import PetStage from "./components/PetStage";
import StatusBar from "./components/StatusBar";

export default function App() {
  return (
    <div className="app-shell" data-phase="components">
      <PetStage />
      <StatusBar />
      <EventList />
    </div>
  );
}
