/**
 * usePetContext —— 宠物上下文的**读取与切换**入口（MPF-5，Phase 3.2-B）。
 *
 * 职责边界：
 * - 读：从**唯一** store 取当前宠物（`petContext.selectedPetId`）；
 * - 写：经 store 的 `setSelectedPet`（MPF-2 第 5 个写出口）切换 —— **唯一**写入路径；
 * - 供：把 `AVAILABLE_PETS`（MPF-1 静态目录）暴露给选择器。
 *
 * **禁止**：本文件不触达 API / 不 fetch / 不建 WebSocket / 不派生业务状态 ——
 * 建连归 `useRuntimePush`（PC-1 唯一接线点），本 hook 只提供「选哪只」。
 *
 * 为什么单独成 hook 而不让 `App` 直连 store：`App` 的既有守卫**禁止**出现 `usePetStore`
 * 与任何 store setter（RF-3 / PC-1）。这与 `usePetRuntime` 暴露 `refresh()` 的既有做法同构。
 */

import { useCallback } from "react";

import { AVAILABLE_PETS, type PetOption } from "../config/pets";
import { usePetStore } from "../stores/usePetStore";

/** 宠物上下文（选择器与接线点消费的公开形状）。 */
export interface PetContext {
  /** 当前宠物键；`null` = 默认宠物（不携带 `pet_id`）。 */
  selectedPetId: string | null;
  /** 可用宠物目录（静态常量，MPF-1）。 */
  availablePets: readonly PetOption[];
  /** 切换当前宠物；传 `null` 回到默认宠物。 */
  selectPet: (petId: string | null) => void;
}

/** 宠物上下文 hook：读 store 当前宠物 + 暴露切换函数与静态目录。 */
export function usePetContext(): PetContext {
  const selectedPetId = usePetStore((s) => s.petContext.selectedPetId);

  const selectPet = useCallback((petId: string | null): void => {
    usePetStore.getState().setSelectedPet(petId);
  }, []);

  return { selectedPetId, availablePets: AVAILABLE_PETS, selectPet };
}
