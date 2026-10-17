import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ApiService } from './api.service';
import { blankEvaluation, CalculationResult, Catalog, EvaluationInput, EvaluationListItem } from './models';

type Step = 'auto' | 'utilizzo' | 'gestione' | 'finanze' | 'analisi';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private api = inject(ApiService);
  private timer?: ReturnType<typeof setTimeout>;
  private calcVersion = 0;

  steps: { id: Step; label: string; short: string; number: string }[] = [
    { id: 'auto', label: 'La tua auto', short: 'Auto', number: '01' },
    { id: 'utilizzo', label: 'Utilizzo', short: 'Utilizzo', number: '02' },
    { id: 'gestione', label: 'Costi di gestione', short: 'Gestione', number: '03' },
    { id: 'finanze', label: 'Budget', short: 'Budget', number: '04' },
    { id: 'analisi', label: 'Analisi', short: 'Risultati', number: '05' },
  ];
  step: Step = 'auto';
  form: EvaluationInput = blankEvaluation();
  result: CalculationResult | null = null;
  catalog: Catalog = {};
  saved: EvaluationListItem[] = [];
  activeId: string | null = null;
  nickname = '';
  nicknameDraft = '';
  sessionTokenDraft = '';
  sessionOpen = true;
  sessionPending = false;
  sessionError = '';
  menuOpen = false;
  busy = false;
  calculating = false;
  saving = false;
  dirty = false;
  toast = '';
  apiError = '';
  showAdvancedResale = false;
  showScenarioSettings = false;
  showMoreCash = false;
  showAssumptions = false;

  readonly conditionOptions = [
    { value: 'new', label: 'Nuova' }, { value: 'km0', label: 'Km zero' },
    { value: 'used', label: 'Usata' }, { value: 'owned', label: 'Già mia' },
  ];
  readonly fuelOptions = [
    { value: 'petrol', label: 'Benzina' }, { value: 'diesel', label: 'Diesel' },
    { value: 'lpg', label: 'GPL' }, { value: 'cng', label: 'Metano' },
    { value: 'hybrid', label: 'Ibrida' }, { value: 'phev', label: 'Plug-in' },
    { value: 'electric', label: 'Elettrica' },
  ];
  readonly brands = ['Alfa Romeo', 'Audi', 'BMW', 'Citroën', 'Dacia', 'Fiat', 'Ford', 'Honda', 'Hyundai', 'Jeep', 'Kia', 'Lancia', 'Mercedes-Benz', 'Mini', 'Nissan', 'Opel', 'Peugeot', 'Renault', 'Škoda', 'Suzuki', 'Tesla', 'Toyota', 'Volkswagen', 'Volvo'];

  ngOnInit() {
    this.api.catalog().subscribe({ next: catalog => this.catalog = catalog, error: () => {} });
    const storedNick = localStorage.getItem('auto.session.nickname');
    const storedToken = localStorage.getItem('auto.session.token');
    if (storedNick && storedToken) {
      this.nickname = storedNick;
      this.nicknameDraft = storedNick;
      this.sessionOpen = false;
      this.loadDraft();
      this.loadSaved();
      if (this.canCalculate) this.recalculate();
    }
  }

  get currentIndex() { return this.steps.findIndex(s => s.id === this.step); }
  get isElectric() { return this.form.vehicle.fuel_type === 'electric'; }
  get isPhev() { return this.form.vehicle.fuel_type === 'phev'; }
  get isCombustion() { return !this.isElectric; }
  get canCalculate() {
    return !!this.form.vehicle.make.trim() && !!this.form.vehicle.model.trim() &&
      Number(this.form.vehicle.purchase_price) > 0 && Number(this.form.usage.years) > 0 &&
      this.form.usage.annual_km !== null && Number(this.form.usage.annual_km) >= 0;
  }
  get carName() {
    return [this.form.vehicle.make, this.form.vehicle.model].filter(Boolean).join(' ') || 'La tua auto';
  }
  get titleText() {
    return this.form.title.trim() || this.carName;
  }
  get completion() {
    const checks = [
      !!this.form.vehicle.make, !!this.form.vehicle.model,
      Number(this.form.vehicle.purchase_price) > 0,
      !!this.form.vehicle.registration_date || this.form.vehicle.condition === 'new',
      this.form.vehicle.initial_km !== null,
      this.form.usage.annual_km !== null,
      this.form.usage.consumption_per_100km !== null || this.isElectric,
      this.form.usage.energy_price !== null || this.isElectric,
      this.form.insurance.online_annual !== null || this.form.insurance.agency_annual !== null,
      this.form.tax.annual !== null,
      this.form.tyres.base_set_price !== null || this.form.tyres.good_set_price !== null,
      this.form.maintenance.service_cost !== null,
      this.form.budget.net_monthly_income !== null,
    ];
    return Math.round(checks.filter(Boolean).length / checks.length * 100);
  }
  get numericSummary() { return this.result?.summary || {}; }
  get affordabilityLabel() {
    const code = this.numericSummary['affordability_label'];
    const labels: Record<string, string> = {
      sostenibile_con_margine: 'Sostenibile con margine',
      sostenibile_con_compromessi: 'Sostenibile con compromessi',
      fragile_agli_imprevisti: 'Fragile agli imprevisti',
      non_sostenibile: 'Non sostenibile',
      dati_insufficienti: 'Dati insufficienti',
    };
    return labels[code] || (typeof code === 'string' ? this.prettyKey(code) : 'Dati da completare');
  }
  get warnings(): string[] {
    const items = this.result?.warnings || [];
    return Array.isArray(items) ? items.map(v => typeof v === 'string' ? v : v?.message || JSON.stringify(v)) : [];
  }
  get missingData(): string[] {
    const data = this.numericSummary['missing_data'];
    return Array.isArray(data) ? data.map(String) : [];
  }
  get selectedInsurancePrice() {
    return this.form.insurance.channel === 'online' ? this.form.insurance.online_annual : this.form.insurance.agency_annual;
  }
  get selectedTyrePrice() {
    return this.form.tyres.tier === 'base' ? this.form.tyres.base_set_price : this.form.tyres.good_set_price;
  }
  get selectedModels() {
    return this.catalog.makes?.find(x => x.name.toLocaleLowerCase() === this.form.vehicle.make.toLocaleLowerCase())?.models || [];
  }
  get projectedKm() {
    return (Number(this.form.vehicle.initial_km) || 0) + (Number(this.form.usage.annual_km) || 0) * (Number(this.form.usage.years) || 0);
  }

  startSession() {
    const nick = this.nicknameDraft.trim();
    if (nick.length < 2 || nick.length > 32) {
      this.sessionError = 'Scegli un nickname tra 2 e 32 caratteri.';
      return;
    }
    this.sessionPending = true;
    this.sessionError = '';
    const rememberedToken = localStorage.getItem(`auto.session.token.${nick.toLocaleLowerCase('it-IT')}`);
    const activeToken = nick.toLocaleLowerCase('it-IT') === this.nickname.toLocaleLowerCase('it-IT')
      ? localStorage.getItem('auto.session.token') : null;
    const token = this.sessionTokenDraft.trim() || rememberedToken || activeToken || '';
    this.api.session(nick, token).subscribe({
      next: data => {
        localStorage.setItem('auto.session.nickname', data.nickname);
        localStorage.setItem('auto.session.token', data.token);
        localStorage.setItem(`auto.session.token.${data.nickname.toLocaleLowerCase('it-IT')}`, data.token);
        this.nickname = data.nickname;
        this.sessionOpen = false;
        this.sessionPending = false;
        this.sessionTokenDraft = '';
        this.activeId = null;
        this.form = blankEvaluation();
        this.result = null;
        this.loadDraft();
        this.loadSaved();
        if (this.canCalculate) this.recalculate();
      },
      error: error => {
        this.sessionPending = false;
        this.sessionError = error.status === 409
          ? 'Questo nickname esiste già. Incolla il suo codice di accesso oppure scegli un altro nickname.'
          : this.errorText(error);
      },
    });
  }

  openSession() {
    this.nicknameDraft = this.nickname;
    this.sessionTokenDraft = '';
    this.sessionOpen = true;
    this.menuOpen = false;
  }

  async copyAccessCode() {
    const token = localStorage.getItem('auto.session.token') || '';
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      this.flash('Codice copiato. Conservalo in privato.');
    } catch {
      this.sessionTokenDraft = token;
      this.flash('Copia il codice dal campo qui sopra.');
    }
  }

  private loadDraft() {
    try {
      const raw = localStorage.getItem(`auto.draft.${this.nickname}`);
      if (raw) {
        const draft = JSON.parse(raw);
        if (draft && typeof draft === 'object') this.form = this.mergeInput(draft);
      }
    } catch { /* Ignore a damaged local draft. */ }
  }

  private persistDraft() {
    if (this.nickname) localStorage.setItem(`auto.draft.${this.nickname}`, JSON.stringify(this.form));
  }

  private mergeInput(input: Partial<EvaluationInput>): EvaluationInput {
    const defaults = blankEvaluation();
    const merged: any = { ...defaults, ...input };
    for (const key of ['vehicle', 'usage', 'insurance', 'tax', 'tyres', 'maintenance', 'revision', 'financing', 'budget', 'scenarios'] as const) {
      merged[key] = { ...defaults[key], ...(input[key] || {}) };
    }
    merged.maintenance.events = Array.isArray(merged.maintenance.events) ? merged.maintenance.events : [];
    return merged as EvaluationInput;
  }

  loadSaved() {
    this.api.list().subscribe({
      next: items => this.saved = Array.isArray(items) ? items : [],
      error: error => {
        if (error.status === 401 || error.status === 403) this.openSession();
        else this.apiError = this.errorText(error);
      },
    });
  }

  newEvaluation() {
    this.activeId = null;
    this.form = blankEvaluation();
    this.result = null;
    this.dirty = false;
    this.step = 'auto';
    this.menuOpen = false;
    this.apiError = '';
    this.persistDraft();
  }

  openEvaluation(id: string) {
    this.busy = true;
    this.api.get(id).subscribe({
      next: item => {
        this.activeId = item.id;
        this.form = this.mergeInput(item.input);
        this.result = item.result;
        this.step = 'analisi';
        this.busy = false;
        this.dirty = false;
        this.menuOpen = false;
        this.apiError = '';
        this.persistDraft();
      },
      error: error => { this.busy = false; this.apiError = this.errorText(error); },
    });
  }

  duplicateEvaluation() {
    this.activeId = null;
    this.form.title = this.titleText + ' · copia';
    this.dirty = true;
    this.persistDraft();
    this.flash('Copia pronta: salva per aggiungerla allo storico.');
  }

  deleteEvaluation() {
    if (this.activeId === null) return;
    if (!window.confirm(`Eliminare “${this.titleText}” dallo storico?`)) return;
    const id = this.activeId;
    this.api.delete(id).subscribe({
      next: () => { this.newEvaluation(); this.loadSaved(); this.flash('Valutazione eliminata.'); },
      error: error => this.apiError = this.errorText(error),
    });
  }

  setStep(step: Step) {
    this.step = step;
    this.menuOpen = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  nextStep() {
    const next = this.steps[Math.min(this.currentIndex + 1, this.steps.length - 1)];
    this.setStep(next.id);
    if (next.id === 'analisi') this.recalculate();
  }

  markChanged() {
    this.dirty = true;
    this.apiError = '';
    this.persistDraft();
    this.scheduleRecalculate();
  }

  private scheduleRecalculate() {
    if (this.timer) clearTimeout(this.timer);
    if (!this.canCalculate) { this.result = null; return; }
    this.timer = setTimeout(() => this.recalculate(), 700);
  }

  recalculate() {
    if (!this.canCalculate) {
      this.apiError = 'Inserisci marca, modello, prezzo d’acquisto, durata e chilometri annui per avviare il calcolo.';
      return;
    }
    const version = ++this.calcVersion;
    this.calculating = true;
    this.api.calculate(this.form).subscribe({
      next: result => {
        if (version !== this.calcVersion) return;
        this.result = result;
        this.calculating = false;
        this.apiError = '';
      },
      error: error => {
        if (version !== this.calcVersion) return;
        this.calculating = false;
        this.apiError = this.errorText(error);
      },
    });
  }

  saveEvaluation() {
    if (!this.canCalculate) {
      this.apiError = 'Completa marca, modello, prezzo d’acquisto, durata e chilometri annui prima di salvare.';
      return;
    }
    this.saving = true;
    this.apiError = '';
    const request = this.activeId !== null ? this.api.update(this.activeId, this.form) : this.api.create(this.form);
    request.subscribe({
      next: item => {
        this.activeId = item.id;
        this.result = item.result;
        this.saving = false;
        this.dirty = false;
        this.loadSaved();
        this.flash('Valutazione salvata.');
      },
      error: error => { this.saving = false; this.apiError = this.errorText(error); },
    });
  }

  loadDemo() {
    this.activeId = null;
    this.form = this.mergeInput({
      title: 'Esempio · Fiat Panda usata',
      vehicle: { ...blankEvaluation().vehicle, make: 'Fiat', model: 'Panda', trim: '1.2', condition: 'used', fuel_type: 'petrol', purchase_price: 12000, purchase_fees: 550, registration_date: '2021-06-01', initial_km: 65000, residual_source: '' },
      usage: { ...blankEvaluation().usage, years: 4, annual_km: 15000, consumption_per_100km: 6, energy_price: 1.8 },
      insurance: { channel: 'online', online_annual: 650, agency_annual: 890, annual_increase_pct: 0 },
      tax: { annual: 180, super_annual: 0, annual_increase_pct: 0, next_due_date: '' },
      tyres: { ...blankEvaluation().tyres, tier: 'good', base_set_price: 320, good_set_price: 480, initial_remaining_km: 20000, initial_remaining_years: 3 },
      maintenance: { ...blankEvaluation().maintenance, service_cost: 300, repairs_annual: 300, other_annual: 360, initial_remaining_service_km: 15000, initial_remaining_service_months: 12 },
      revision: { cost: 80, last_revision_date: '2025-06-01' },
      budget: { ...blankEvaluation().budget, net_monthly_income: 2200, other_monthly_expenses: 1100, min_monthly_savings: 250, available_cash: 18000, emergency_reserve: 6000 },
    });
    this.dirty = true;
    this.persistDraft();
    this.setStep('analisi');
    this.recalculate();
    this.flash('Esempio illustrativo caricato. Puoi cambiare ogni cifra.');
  }

  addEvent() {
    this.form.maintenance.events.push({ year: 1, cost: null, label: '' });
    this.markChanged();
  }

  removeEvent(index: number) {
    this.form.maintenance.events.splice(index, 1);
    this.markChanged();
  }

  selectCondition(value: EvaluationInput['vehicle']['condition']) {
    this.form.vehicle.condition = value;
    this.markChanged();
  }
  selectInsurance(value: EvaluationInput['insurance']['channel']) {
    this.form.insurance.channel = value;
    this.markChanged();
  }
  selectTyre(value: EvaluationInput['tyres']['tier']) {
    this.form.tyres.tier = value;
    this.markChanged();
  }
  selectFinance(value: boolean) {
    this.form.financing.enabled = value;
    this.markChanged();
  }

  value(key: string): number | null {
    const raw = this.numericSummary[key];
    const n = Number(raw);
    return raw === null || raw === undefined || !Number.isFinite(n) ? null : n;
  }

  euro(value: any, digits = 0): string {
    const n = Number(value);
    return value === null || value === undefined || !Number.isFinite(n) ? '—' : new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  }

  number(value: any, digits = 0): string {
    const n = Number(value);
    return value === null || value === undefined || !Number.isFinite(n) ? '—' : new Intl.NumberFormat('it-IT', { maximumFractionDigits: digits }).format(n);
  }

  percent(value: any): string {
    const n = Number(value);
    return value === null || value === undefined || !Number.isFinite(n) ? '—' : `${new Intl.NumberFormat('it-IT', { maximumFractionDigits: 1 }).format(n * 100)}%`;
  }

  get breakdownRows(): { key: string; label: string; total: number; monthly: number; color: string }[] {
    const b = this.result?.breakdown;
    const months = Number(this.form.usage.years) * 12 || 1;
    const labels: Record<string, string> = {
      depreciation: 'Svalutazione', purchase_fees: 'Spese iniziali', acquisition: 'Spese iniziali',
      financing: 'Costo del credito', credit: 'Costo del credito', credit_cost: 'Costo del credito',
      fuel: 'Carburante / energia', energy: 'Carburante / energia', insurance: 'Assicurazione',
      tax: 'Bollo e superbollo', tyres: 'Pneumatici', maintenance: 'Tagliandi e manutenzione',
      service: 'Tagliandi', revision: 'Revisioni', repairs: 'Riparazioni', other: 'Altre spese',
    };
    const colors = ['#b6d6a3', '#f3bc85', '#a9c7db', '#d8bcdf', '#e9d89c', '#8fb8a4', '#eaa9a0', '#c2bcab'];
    if (b && !Array.isArray(b) && typeof b === 'object') {
      const rows = Object.entries(b).map(([key, raw], i) => {
        const value = typeof raw === 'number' ? raw : Number((raw as any)?.total ?? (raw as any)?.amount ?? raw);
        return { key, label: labels[key] || this.prettyKey(key), total: value, monthly: value / months, color: colors[i % colors.length] };
      }).filter(row => Number.isFinite(row.total));
      if (rows.length) return rows;
    }
    return [
      { key: 'depreciation', label: 'Svalutazione', total: Number(this.value('depreciation') || 0), monthly: Number(this.value('depreciation') || 0) / months, color: colors[0] },
      { key: 'management', label: 'Gestione', total: Number(this.value('management_total') || 0), monthly: Number(this.value('management_total') || 0) / months, color: colors[1] },
      { key: 'credit', label: 'Credito', total: Number(this.value('credit_cost') || 0), monthly: Number(this.value('credit_cost') || 0) / months, color: colors[2] },
    ].filter(row => row.total !== 0);
  }

  get breakdownMax() { return Math.max(...this.breakdownRows.map(x => Math.abs(x.total)), 1); }
  get annualRows(): Record<string, any>[] { return Array.isArray(this.result?.annual) ? this.result!.annual! : []; }
  get cashCalendar(): Record<string, any>[] { return Array.isArray(this.result?.cash_calendar) ? this.result!.cash_calendar! : []; }
  get durations(): Record<string, any>[] { return Array.isArray(this.result?.comparisons?.durations) ? this.result!.comparisons.durations : []; }
  get insuranceComparison(): Record<string, any> { return this.result?.comparisons?.insurance || {}; }
  get tyreComparison(): Record<string, any> { return this.result?.comparisons?.tyres || {}; }
  get scenarioRows(): { key: string; label: string; data: any }[] {
    const data = this.result?.scenarios;
    if (!data || typeof data !== 'object') return [];
    if (Array.isArray(data)) return data.map((x: any, i: number) => ({ key: String(i), label: x.label || x.name || `Scenario ${i + 1}`, data: x }));
    return Object.entries(data).map(([key, value]) => ({ key, label: this.prettyKey(key), data: value }));
  }
  get comparisonRows(): { key: string; label: string; data: any }[] {
    const data = this.result?.comparisons;
    if (!data || typeof data !== 'object') return [];
    return Object.entries(data).map(([key, value]) => ({ key, label: this.prettyKey(key), data: value }));
  }
  objectPairs(value: any): { key: string; label: string; value: any }[] {
    if (!value || typeof value !== 'object') return [];
    return Object.entries(value).filter(([, v]) => typeof v === 'number' || typeof v === 'string').map(([key, val]) => ({ key, label: this.prettyKey(key), value: val }));
  }
  prettyKey(key: string): string {
    const labels: Record<string, string> = {
      total: 'Totale', monthly: 'Al mese', annual: 'All’anno', year: 'Anno',
      monthly_cost: 'Costo mensile', total_cost: 'Costo totale', cash_monthly: 'Uscita mensile',
      income_ratio: 'Quota del reddito', residual_value: 'Rivendita',
      central: 'Centrale', prudent: 'Prudente', adverse: 'Avverso',
      online: 'Online', agency: 'Agenzia', base: 'Gomme base', good: 'Gomme buone',
      depreciation: 'Svalutazione', insurance: 'Assicurazione', fuel: 'Energia / carburante',
    };
    return labels[key] || key.replace(/_/g, ' ').replace(/^./, c => c.toLocaleUpperCase('it-IT'));
  }
  formatMetric(key: string, val: any): string {
    if (typeof val !== 'number') return String(val ?? '—');
    if (key.includes('ratio') || key.endsWith('_pct')) return key.endsWith('_pct') ? `${this.number(val, 1)}%` : this.percent(val);
    if (key.includes('km') || key === 'year') return this.number(val);
    return this.euro(val, 0);
  }

  private errorText(error: HttpErrorResponse): string {
    const apiMessage = error.error?.error?.message || error.error?.error || error.error?.message;
    if (typeof apiMessage === 'string') return apiMessage;
    if (error.status === 0) return 'Il server non risponde. Riprova tra poco.';
    return 'Operazione non riuscita. Controlla i dati e riprova.';
  }

  private flash(message: string) {
    this.toast = message;
    setTimeout(() => { if (this.toast === message) this.toast = ''; }, 4500);
  }
}
