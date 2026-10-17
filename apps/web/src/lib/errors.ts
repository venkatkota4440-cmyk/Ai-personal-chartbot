import { ApiError } from "@/lib/api";

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, "internal_error", "Unexpected error");
}

/** AI failures happen after the server has saved the user's message, so the draft is already stored. */
export function messageWasSaved(error: ApiError): boolean {
  return error.category === "ai_unavailable" || error.category === "ai_invalid_output" || error.category === "ai_refused";
}
