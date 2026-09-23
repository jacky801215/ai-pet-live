/**
 * PetStage —— 宠物展示区域（FCM-2 / RB-1 / RB-3）。
 *
 * 舞台容器：只负责 container / layout 与内嵌 PetPlayer（RB-1）；
 * **不消费 asset_url**——全页面唯一媒体消费者是 PetPlayer（RB-3）；
 * 空态由 PetPlayer 的既有空态表达。本组件不做任何网络请求、不持有状态、不判断素材类型（RB-2）。
 *
 * **§7.1 收口（受权增量）**：新增**可选** prop `placeholder` 并原样透传给 `PetPlayer`。
 * 本组件**仍不消费 store**（RB-1 守卫不变），该布尔值由 `App` 计算后经 prop 注入。
 */
import PetPlayer from "./player/PetPlayer";

export interface PetStageProps {
  /** 当前选中宠物是否为「素材待接入」占位宠物（§7.1；缺省 `false`）。 */
  placeholder?: boolean;
}

export default function PetStage({ placeholder = false }: PetStageProps) {
  return (
    <section className="pet-stage" data-testid="pet-stage">
      <PetPlayer placeholder={placeholder} />
    </section>
  );
}
