export interface CustomerSearchResult {
  customer_number: number;
  customer_name: string;
  dba_name: string;
  route_code: string;
  store_number: number | null;
  salesman_number: number | null;
  customer_type: string;
  customer_class: string;
  active: boolean;
  phone: string;
  email: string;
  address_line_1?: string;
  address_line_2?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  postal_code?: string;
  credit_limit: number;
  balance: number;
  on_order: number;
  credit_on_order: number;
  exposure: number;
  available_credit: number;
  amount_over_limit: number;
  utilization_percent: number | null;
  past_due_amount: number;
  is_over_limit: boolean;
  is_past_due: boolean;
}

export type CustomerRiskPriority = "Critical" | "High" | "Elevated";

export interface CustomerRiskReviewItem extends CustomerSearchResult {
  rank: number;
  risk_score: number;
  risk_priority: CustomerRiskPriority;
  risk_reasons: string[];
  days_60_plus: number;
  days_90_plus: number;
}

export interface CustomerSearchResponse {
  customers: CustomerSearchResult[];
  count: number;
  limit: number;
  offset: number;
}

export interface CustomerRiskReviewResponse {
  customers: CustomerRiskReviewItem[];
  count: number;
  threshold_percent: number;
  generated_at: string;
  criteria: string[];
}

export interface CustomerSummary {
  customer_number: number;
  customer_name: string;
  general: {
    dba_name: string;
    address_lines: string[];
    address_line_1?: string;
    address_line_2?: string;
    city?: string;
    state?: string;
    state_abbreviation?: string;
    postal_code?: string;
    state_code: number | null;
    zip_code: string;
    country: string;
    phone: string;
    fax: string;
    email: string;
    contact: string;
    route_code: string;
    store_number: number | null;
    home_site: number | null;
    salesman_number: number | null;
    customer_type: string;
    customer_class: string;
    active: boolean;
    delete_code: string;
  };
  credit: {
    credit_limit: number;
    balance: number;
    on_order: number;
    on_order_ar: number;
    raw_on_order: number;
    credit_on_order: number;
    total_exposure: number;
    available_credit: number;
    amount_over_limit?: number;
    is_over_limit?: boolean;
    utilization_percent: number | null;
    high_balance: number;
    monthly_high_balance: number;
    average_daily_balance: number;
    terms_code: string;
    terms_description: string;
    credit_grade: string;
    grade_code: string;
    credit_opened_date: string | null;
    credit_limit_expiration: string | null;
    letter_of_credit_expiration: string | null;
  };
  aging: {
    future: number;
    current: number;
    days_30: number;
    days_60: number;
    days_90: number;
    days_120: number;
    past_due: number;
    total_aging: number;
  };
  sales: {
    month_to_date: number;
    year_to_date: number;
    last_year: number;
    month_to_date_discounts: number;
    year_to_date_discounts: number;
    annualized_sales: number;
    expected_credit_line: number;
  };
  activity: Record<string, string | number | null>;
  flags: Record<string, string | boolean | null>;
}

export interface CustomerAiSummaryResponse {
  summary: string;
  model: string;
  generated_at: string;
}
