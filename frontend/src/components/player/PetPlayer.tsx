/**
 * PetPlayer —— 当前动作播放展示（FCM-2 / FCM-3 + FP-1..FP-5）。
 *
 * 数据只经 `usePetStore()` 读取；媒体输入**唯一**来源 `playback.asset_url`（FP-2）：
 * - `asset_url !== null` → 渲染原生 `<video>`（FP-3 属性白名单）；
 * - `asset_url === null` → 不渲染媒体区域，保留 playback snapshot 文本展示（FP-2 v1.1）；
 * - `loop` 属性**只消费** `playback.loop`（**CR-1**）：不在组件内判断动作语义（FP-3 v1.2）。
 * 不保存播放状态（FP-4）：无 useState / useEffect / ref / currentTime / progress / onEnded 回写。
 * 本组件不做任何网络请求、不拼接 URL、不用计时器、不引入第三方播放器。
 *
 * **§7.1 收口（受权增量）**：新增**可选** prop `placeholder`（当前宠物是否素材待接入）——
 * 由 `App` 经 `PetStage` 注入，组件**不**自行获取目录（组件数据只经 store 读，故不新增 import）。
 * 为 `true` 时在视频区域附一条提示文本；`<video>` 的渲染条件与 `src` 逻辑**逐字不变**。
 */
import { usePetStore } from "../../stores/usePetStore";

export interface PetPlayerProps {
  /**
   * 当前选中宠物是否为「素材待接入」占位宠物（§7.1；缺省 `false`）。
   *
   * 由 `App`（读 `usePetContext().availablePets`）经 `PetStage` 注入 ——
   * 本组件不 import 宠物目录，维持"组件只经 store 读数据"的既有边界。
   */
  placeholder?: boolean;
}

export default function PetPlayer({ placeholder = false }: PetPlayerProps) {
  const playback = usePetStore((s) => s.playback);

  if (playback === null) {
    return (
      <div className="pet-player pet-player--empty" data-testid="pet-player-empty">
        暂无播放内容
      </div>
    );
  }

  return (
    <div className="pet-player" data-testid="pet-player">
      {playback.asset_url !== null ? (
        <video
          className="pet-player__media"
          src={playback.asset_url}
          autoPlay
          muted
          playsInline
          controls={false}
          loop={playback.loop}
          data-testid="pet-player-media"
        />
      ) : null}
      {placeholder ? (
        <span className="pet-player__hint" data-testid="pet-player-placeholder-hint">
          该宠物素材待接入
        </span>
      ) : null}
      <span className="pet-player__pet-id" data-testid="pet-player-pet-id">
        宠物：{playback.pet_id}
      </span>
      <span className="pet-player__state" data-testid="pet-player-state">
        状态：{playback.state}
      </span>
      <span className="pet-player__action" data-testid="pet-player-action">
        动作：{playback.action ?? "—"}
      </span>
    </div>
  );
}
