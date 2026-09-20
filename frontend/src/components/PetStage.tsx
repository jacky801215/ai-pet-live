/**
 * PetStage —— 宠物展示区域（FCM-2 / RB-1 / RB-3）。
 *
 * 舞台容器：只负责 container / layout 与内嵌 PetPlayer（RB-1）；
 * **不消费 asset_url**——全页面唯一媒体消费者是 PetPlayer（RB-3）；
 * 空态由 PetPlayer 的既有空态表达。本组件不做任何网络请求、不持有状态、不判断素材类型（RB-2）。
 */
import PetPlayer from "./player/PetPlayer";

export default function PetStage() {
  return (
    <section className="pet-stage" data-testid="pet-stage">
      <PetPlayer />
    </section>
  );
}
