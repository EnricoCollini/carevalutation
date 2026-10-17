export interface EvaluationInput {
  title: string;
  vehicle: {
    make: string; model: string; trim: string;
    condition: 'new' | 'km0' | 'used' | 'owned';
    fuel_type: 'petrol' | 'diesel' | 'lpg' | 'cng' | 'hybrid' | 'phev' | 'electric';
    purchase_price: number | null; purchase_fees: number | null; trade_in_value: number | null; new_list_price: number | null;
    purchase_date: string; registration_date: string;
    initial_km: number | null; residual_value: number | null;
    residual_value_low: number | null; residual_value_high: number | null;
    residual_source: string; sale_channel: string;
  };
  usage: {
    years: number; annual_km: number | null;
    consumption_per_100km: number | null; energy_price: number | null;
    charging_efficiency: number | null; electric_share: number | null;
    electric_consumption_per_100km: number | null; electric_price: number | null;
  };
  insurance: {
    channel: 'online' | 'agency'; online_annual: number | null;
    agency_annual: number | null; annual_increase_pct: number;
  };
  tax: { annual: number | null; super_annual: number | null; annual_increase_pct: number; next_due_date: string };
  tyres: {
    tier: 'base' | 'good'; type: 'all_season' | 'summer' | 'winter' | 'seasonal';
    base_set_price: number | null; good_set_price: number | null;
    life_km: number | null; life_years: number | null;
    initial_remaining_km: number | null; initial_remaining_years: number | null;
    seasonal_change_annual: number | null; storage_annual: number | null;
  };
  maintenance: {
    service_cost: number | null; service_interval_km: number | null;
    service_interval_months: number | null; initial_remaining_service_km: number | null;
    initial_remaining_service_months: number | null; repairs_annual: number | null;
    other_annual: number | null; events: { year: number; cost: number | null; label: string }[];
  };
  revision: { cost: number | null; last_revision_date: string };
  financing: {
    enabled: boolean; down_payment: number | null; loan_amount: number | null;
    term_months: number | null; tan_pct: number | null; balloon: number | null;
    origination_fee: number | null; monthly_fee: number | null; settlement_fee: number | null;
  };
  budget: {
    net_monthly_income: number | null; annual_payments: 12 | 13 | 14;
    other_monthly_expenses: number | null; min_monthly_savings: number | null;
    available_cash: number | null; emergency_reserve: number | null;
    emergency_months: number | null; target_replacement_price: number | null;
  };
  scenarios: {
    fuel_increase_pct: number; insurance_increase_pct: number;
    maintenance_increase_pct: number; residual_drop_pct: number;
    income_drop_pct: number; extra_repair: number;
  };
}

export interface CalculationResult {
  summary?: Record<string, any>;
  breakdown?: any;
  annual?: any[];
  cash_calendar?: any[];
  events?: any[];
  scenarios?: any;
  purchase_estimate?: { low: number; central: number; high: number; offered_price: number; difference_from_estimate: number; position: string; method: string; source: string } | null;
  comparisons?: any;
  assumptions?: any;
  warnings?: any[];
}

export interface SavedEvaluation {
  id: string;
  title: string;
  input: EvaluationInput;
  result: CalculationResult;
  created_at: string;
  updated_at: string;
}

export interface EvaluationListItem {
  id: string;
  title: string;
  vehicle?: any;
  summary?: Record<string, any>;
  updated_at: string;
}

export interface Catalog {
  makes?: { name: string; models: string[] }[];
  defaults?: Record<string, any>;
  options?: Record<string, any>;
}

export function blankEvaluation(): EvaluationInput {
  const today = new Date().toISOString().slice(0, 10);
  return {
    title: '',
    vehicle: {
      make: '', model: '', trim: '', condition: 'used', fuel_type: 'petrol',
      purchase_price: null, purchase_fees: null, trade_in_value: null, new_list_price: null, purchase_date: today,
      registration_date: '', initial_km: null, residual_value: null,
      residual_value_low: null, residual_value_high: null, residual_source: '',
      sale_channel: 'private',
    },
    usage: {
      years: 4, annual_km: 15000, consumption_per_100km: null,
      energy_price: null, charging_efficiency: 0.9, electric_share: null,
      electric_consumption_per_100km: null, electric_price: null,
    },
    insurance: { channel: 'online', online_annual: null, agency_annual: null, annual_increase_pct: 0 },
    tax: { annual: null, super_annual: null, annual_increase_pct: 0, next_due_date: '' },
    tyres: {
      tier: 'good', type: 'all_season', base_set_price: null, good_set_price: null,
      life_km: 40000, life_years: 5, initial_remaining_km: null,
      initial_remaining_years: null, seasonal_change_annual: null, storage_annual: null,
    },
    maintenance: {
      service_cost: null, service_interval_km: 15000, service_interval_months: 12,
      initial_remaining_service_km: null, initial_remaining_service_months: null,
      repairs_annual: null, other_annual: null, events: [],
    },
    revision: { cost: null, last_revision_date: '' },
    financing: {
      enabled: false, down_payment: null, loan_amount: null, term_months: 48,
      tan_pct: null, balloon: null, origination_fee: null, monthly_fee: null,
      settlement_fee: null,
    },
    budget: {
      net_monthly_income: null, annual_payments: 13, other_monthly_expenses: null,
      min_monthly_savings: null, available_cash: null, emergency_reserve: null,
      emergency_months: 3, target_replacement_price: null,
    },
    scenarios: {
      fuel_increase_pct: 20, insurance_increase_pct: 20,
      maintenance_increase_pct: 30, residual_drop_pct: 20,
      income_drop_pct: 10, extra_repair: 1000,
    },
  };
}
