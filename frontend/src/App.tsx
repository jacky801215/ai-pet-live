/**
 * App —— Phase 1 单窗口外壳（UB-3 / FCM-2 / FD-1：组合 + 初始化数据流）。
 *
 * 唯一新增职责（FD-2 / FD-3）：调用一次 usePetRuntime() 触发初次加载；
 * 数据经 store 流向各组件（Store ↓ Component），App 自身不取数据、不写 setter。
 */
import EventList from "./components/EventList";
import PetStage from "./components/PetStage";
import StatusBar from "./components/StatusBar";
import { usePetRuntime } from "./hooks/usePetRuntime";

export default function App() {
  usePetRuntime();

  return (
    <div className="app-shell" data-phase="components">
      <PetStage />
      <StatusBar />
      <EventList />
    </div>
  );
}
