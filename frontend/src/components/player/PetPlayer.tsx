/**
 * PetPlayer —— 当前动作播放展示（FCM-2，FCM-3）。
 *
 * 数据只经 `usePetStore()` 读取；本组件不做任何网络请求、不建播放状态、不用计时器。
 * 展示字段以冻结契约为准：`pet_id` / `state`（"idle" | "playing"）/ `action`（可空）。
 */
import { usePetStore } from "../../stores/usePetStore";

export default function PetPlayer() {
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
