/**
 * PetPlayer —— 当前动作播放展示（FCM-2 / FCM-3 + FP-1..FP-5）。
 *
 * 数据只经 `usePetStore()` 读取；媒体输入**唯一**来源 `playback.asset_url`（FP-2）：
 * - `asset_url !== null` → 渲染原生 `<video>`（FP-3 属性白名单）；
 * - `asset_url === null` → 不渲染媒体区域，保留 playback snapshot 文本展示（FP-2 v1.1）。
 * 不保存播放状态（FP-4）：无 useState / useEffect / ref / currentTime / progress / onEnded 回写。
 * 本组件不做任何网络请求、不拼接 URL、不用计时器、不引入第三方播放器。
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
      {playback.asset_url !== null ? (
        <video
          className="pet-player__media"
          src={playback.asset_url}
          autoPlay
          muted
          playsInline
          controls={false}
          data-testid="pet-player-media"
        />
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
