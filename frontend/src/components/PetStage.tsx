/**
 * PetStage —— 宠物展示区域（FCM-2，FCM-3）。
 *
 * 内嵌 PetPlayer；素材地址**只消费** `playback.asset_url`（后端已解析的对外地址，
 * UB-4 / FCM-4），本组件不生成、不改写任何地址。
 */
import { usePetStore } from "../stores/usePetStore";
import PetPlayer from "./player/PetPlayer";

export default function PetStage() {
  const assetUrl = usePetStore((s) => s.playback?.asset_url ?? null);

  return (
    <section className="pet-stage" data-testid="pet-stage">
      <PetPlayer />
      {assetUrl !== null ? (
        <img
          className="pet-stage__asset"
          src={assetUrl}
          alt="当前动作素材"
          data-testid="pet-stage-asset"
        />
      ) : (
        <p className="pet-stage__empty" data-testid="pet-stage-empty">
          暂无宠物画面
        </p>
      )}
    </section>
  );
}
