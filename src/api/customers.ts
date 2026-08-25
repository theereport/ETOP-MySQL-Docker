import { requestJson } from "./client";
import type {
  CustomerAiSummaryResponse,
  CustomerRiskReviewResponse,
  CustomerSearchResponse,
  CustomerSummary,
} from "../features/customer360/types";

export async function searchCustomers(
  search: string,
  signal?: AbortSignal,
  activeOnly = true,
): Promise<CustomerSearchResponse> {
  const params = new URLSearchParams({
    search,
    limit: "100",
    active_only: String(activeOnly),
  });
  return requestJson<CustomerSearchResponse>(`/customers?${params.toString()}`, { signal });
}
export async function getCustomerSummary(customerNumber: number | string, signal?: AbortSignal): Promise<CustomerSummary> {
  return requestJson<CustomerSummary>(`/customers/${encodeURIComponent(String(customerNumber))}`, { signal });
}
export async function getCustomerRiskReview(
  signal?: AbortSignal,
): Promise<CustomerRiskReviewResponse> {
  const params = new URLSearchParams({
    limit: "100",
    minimum_utilization: "75",
  });
  return requestJson<CustomerRiskReviewResponse>(
    `/customer-risk/review?${params.toString()}`,
    { signal },
  );
}
export async function generateCustomerAiSummary(payload: unknown, signal?: AbortSignal): Promise<CustomerAiSummaryResponse> {
  return requestJson<CustomerAiSummaryResponse>("/customer-intelligence/summary", { method: "POST", body: payload, signal });
}
