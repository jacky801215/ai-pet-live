/**
 * HTTP 传输层 —— 全前端**唯一**发出 `fetch` 的位置（FC-2）。
 *
 * 边界（UB-1 / FC-5）：
 * - 只做「发请求、收响应、把 **HTTP 非 2xx** 转成 {@link ApiError}」；
 * - **禁止**业务错误判断（不得解读后端 code 的业务含义）、**禁止**改写后端 code、
 *   **禁止**吞错误（网络层异常原样上抛，不折叠）；
 * - **禁止**出现任何具体端点知识（路径归各 API module）与 React / store 概念。
 */

/** API 层错误：仅由 **HTTP 非 2xx** 转换而来（FC-5）。 */
export class ApiError extends Error {
  /** HTTP 状态码（后端契约：400 / 404 / 500）。 */
  public readonly status: number;
  /** 后端统一错误体的 `code`（**原样透传**，不改写不解读；错误体缺失时为空串）。 */
  public readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** API 基地址：默认同源（生产由后端静态托管）；开发可用 `VITE_API_BASE` 指向后端。 */
const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

/**
 * 发起一次 JSON 请求并解析响应。
 *
 * @typeParam TResponse - 响应 DTO（见 `src/types/api.ts`，与后端契约逐字段一致）。
 * @throws {ApiError} HTTP 非 2xx（`code` / `message` 取自后端统一错误体）。
 * @throws 网络层异常原样上抛（本层**不**捕获、**不**包装、**不**重试）。
 */
export async function request<TResponse>(
  path: string,
  init?: RequestInit,
): Promise<TResponse> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init?.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
  });

  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as TResponse;
}

/** 把「HTTP 非 2xx」转换为 {@link ApiError}（错误体非 JSON 时保留状态码与 statusText，不吞错）。 */
async function toApiError(response: Response): Promise<ApiError> {
  let code = "";
  let message = response.statusText || `HTTP ${response.status}`;
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object") {
      const record = body as Record<string, unknown>;
      if (typeof record.code === "string") {
        code = record.code;
      }
      if (typeof record.message === "string") {
        message = record.message;
      }
    }
  } catch {
    // 错误体不是合法 JSON：保留 HTTP 状态与 statusText —— 状态本身即信息，不吞。
  }
  return new ApiError(response.status, code, message);
}
