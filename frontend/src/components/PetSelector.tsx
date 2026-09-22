/**
 * PetSelector —— 宠物上下文选择器（**MPF-5**，Phase 3.2-B）。
 *
 * 职责：把**可用宠物目录**（由 `App` 经 `usePetContext()` 注入）与**当前选择**
 * （`petContext.selectedPetId`，只读 store）渲染成选择控件；切换经 **prop 注入** 的
 * `onSelect(petId)` 交回上层 —— 与 `EventSimulator` 的 `onTrigger` 同构（ES-1）：
 * 组件**不**直写 store setter、**不**持有 state。
 *
 * 边界：
 * - 数据只来自 store 与 props（与 StatusBar / EventList 同口径）；
 * - **禁止**：API import / fetch / WebSocket / 动画计时器 / 派生业务状态 / 本地 state；
 * - 目录值由 `src/config/pets.ts` 收口 ⇒ **只会**产生 backend `known_pet_keys()` 接受的键。
 *
 * 取值约定：内部用空串代表「默认宠物」（`selectedPetId === null`），是本组件**局部**的
 * DOM 值映射（`<select>` 的 value 不能为 null），不外泄到 store。
 */
import type { PetOption } from "../config/pets";
import { usePetStore } from "../stores/usePetStore";

/** 「默认宠物」在 DOM 层的占位值（不等于任何真实 pet 键）。 */
const DEFAULT_OPTION_VALUE = "";

export interface PetSelectorProps {
  /** 可用宠物目录（由 `App` 经 `usePetContext()` 注入；组件不自行获取）。 */
  availablePets: readonly PetOption[];
  /** 切换回调（`null` = 回到默认宠物）。 */
  onSelect: (petId: string | null) => void;
}

export default function PetSelector({ availablePets, onSelect }: PetSelectorProps) {
  const selectedPetId = usePetStore((s) => s.petContext.selectedPetId);

  return (
    <label
      className="pet-selector"
      data-testid="pet-selector"
      data-selected-pet={selectedPetId ?? DEFAULT_OPTION_VALUE}
    >
      <span className="pet-selector__label">宠物</span>
      <select
        className="pet-selector__select"
        data-testid="pet-selector-select"
        value={selectedPetId ?? DEFAULT_OPTION_VALUE}
        onChange={(event) => {
          const raw = event.target.value;
          // MPF-5：空串 ↔ null（默认宠物）的局部映射，只在此处发生
          onSelect(raw === DEFAULT_OPTION_VALUE ? null : raw);
        }}
      >
        <option value={DEFAULT_OPTION_VALUE}>默认宠物</option>
        {availablePets.map((pet) => (
          <option key={pet.pet_id} value={pet.pet_id}>
            {pet.label}
          </option>
        ))}
      </select>
    </label>
  );
}
