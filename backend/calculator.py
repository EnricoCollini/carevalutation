"""Transparent, deterministic car ownership calculations for private buyers in Italy.

Prices supplied by the user are never silently replaced with purported market data.
The internal residual estimator is illustrative, and every assumption is returned.
"""

from __future__ import annotations

from calendar import monthrange
from copy import deepcopy
from datetime import date
from math import exp, isfinite


class CalculationError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _section(data: dict, name: str) -> dict:
    value = data.get(name) or {}
    if not isinstance(value, dict):
        raise CalculationError(name, "Deve essere un oggetto.")
    return value


def _number(obj: dict, key: str, path: str, default=None, minimum=0, maximum=None):
    raw = obj.get(key)
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        raise CalculationError(f"{path}.{key}", "Inserisci un numero valido.")
    try:
        value = float(raw)
    except (ValueError, TypeError):
        raise CalculationError(f"{path}.{key}", "Inserisci un numero valido.") from None
    if not isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise CalculationError(f"{path}.{key}", "Valore fuori dall'intervallo consentito.")
    return value


def _choice(obj: dict, key: str, path: str, allowed: set[str], default: str):
    value = obj.get(key) or default
    if value not in allowed:
        raise CalculationError(f"{path}.{key}", f"Scegli uno fra: {', '.join(sorted(allowed))}.")
    return value


def _date(obj: dict, key: str, path: str, default=None):
    value = obj.get(key)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise CalculationError(f"{path}.{key}", "Usa la data nel formato AAAA-MM-GG.") from None


def _add_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _money(value: float | None):
    return None if value is None else round(value + 1e-9, 2)


def _fraction(value: float | None):
    return None if value is None else round(value, 4)


def _age_years(registration_date: date | None, purchase_date: date, condition: str):
    if registration_date:
        if registration_date > purchase_date:
            raise CalculationError("vehicle.registration_date", "L'immatricolazione non può essere dopo l'acquisto.")
        return (purchase_date - registration_date).days / 365.25, False
    if condition == "new":
        return 0.0, False
    if condition == "km0":
        return 0.25, True
    return 4.0, True


def _retention_at_age(age: float) -> float:
    """Illustrative age curve; used-car value starts at its *current* price."""
    bands = ((1, .78), (2, .88), (3, .90), (6, .92), (10, .94), (50, .96))
    factor = 1.0
    elapsed = 0.0
    for end, yearly in bands:
        span = min(max(age - elapsed, 0.0), end - elapsed)
        factor *= yearly ** span
        elapsed = end
        if age <= end:
            break
    return factor


def estimate_residual(vehicle: dict, usage: dict, months: int, purchase_date: date) -> dict:
    price = _number(vehicle, "purchase_price", "vehicle", 0)
    condition = _choice(vehicle, "condition", "vehicle", {"new", "km0", "used", "owned"}, "used")
    registration = _date(vehicle, "registration_date", "vehicle")
    age, assumed_age = _age_years(registration, purchase_date, condition)
    km_annual = _number(usage, "annual_km", "usage", 0)
    years = months / 12
    initial_km = _number(vehicle, "initial_km", "vehicle", 0)
    sale_channel = _choice(vehicle, "sale_channel", "vehicle", {"private", "dealer", "trade_in"}, "private")
    manual = _number(vehicle, "residual_value", "vehicle", None)
    low_manual = _number(vehicle, "residual_value_low", "vehicle", None)
    high_manual = _number(vehicle, "residual_value_high", "vehicle", None)
    if manual is not None:
        central = manual
        spread = min(.35, .10 + .02 * years)
        low = low_manual if low_manual is not None else max(0, central * (1 - spread))
        high = high_manual if high_manual is not None else central * (1 + spread)
        if low > central or high < central:
            raise CalculationError("vehicle.residual_value", "L'intervallo deve contenere il valore centrale.")
        method = "manuale"
        source = (vehicle.get("residual_source") or "Valore inserito dall'utente").strip()
    else:
        # Compare only depreciation DURING this ownership period. In particular, a
        # used car is not charged for the first-owner depreciation again.
        age_ratio = _retention_at_age(age + years) / _retention_at_age(age)
        # Mileage adjustment is relative to 15,000 km/year from the current odometer.
        # The current purchase price already reflects the first owner's mileage.
        # Absolute high-mileage thresholds also matter as this car crosses them.
        excess_km = km_annual * years - 15000 * years
        future_km = initial_km + km_annual * years
        threshold_crossing = max(0, future_km - 150000) - max(0, initial_km - 150000)
        km_factor = min(1.18, max(.55, exp(-.03 * excess_km / 10000 - .01 * threshold_crossing / 10000)))
        channel_factor = {"private": 1.0, "dealer": .90, "trade_in": .86}[sale_channel]
        central = max(0, price * age_ratio * km_factor * channel_factor)
        spread = min(.38, .14 + .025 * years + (.06 if assumed_age else 0))
        low = max(0, central * (1 - spread))
        high = min(price * 1.10, central * (1 + spread))
        method = "stima_interna_illustrativa"
        source = "Curva illustrativa per età, km e canale di vendita; non è una quotazione di mercato"
    return {
        "central": central, "low": low, "high": high, "method": method,
        "source": source, "age_at_purchase": age, "age_assumed": assumed_age,
        "age_at_sale": age + years, "final_km": initial_km + km_annual * years,
        "sale_channel": sale_channel,
    }


def estimate_purchase_price(vehicle: dict, purchase_date: date) -> dict | None:
    """Optional indicative *current* used price from an original new list price.

    This is deliberately separate from the user's actual dealership offer, which
    remains the only purchase price used by the ownership-cost calculation.
    """
    condition = _choice(vehicle, "condition", "vehicle", {"new", "km0", "used", "owned"}, "used")
    if condition not in ("used", "km0"):
        return None
    original_list = _number(vehicle, "new_list_price", "vehicle", None)
    registration = _date(vehicle, "registration_date", "vehicle")
    current_km = _number(vehicle, "initial_km", "vehicle", None)
    if original_list is None or registration is None or current_km is None:
        return None
    if original_list <= 0:
        raise CalculationError("vehicle.new_list_price", "Il prezzo nuovo originario deve essere maggiore di zero.")
    age, _ = _age_years(registration, purchase_date, condition)
    offered = _number(vehicle, "purchase_price", "vehicle", 0)
    expected_km = 15000 * age
    km_factor = min(1.25, max(.55, exp(-.03 * (current_km - expected_km) / 10000)))
    central = original_list * _retention_at_age(age) * km_factor
    # List prices, discounts, condition and trim options are imperfect proxies.
    spread = min(.45, .22 + .015 * age)
    low = max(0, central * (1 - spread))
    high = central * (1 + spread)
    position = "below_range" if offered < low else ("above_range" if offered > high else "within_range")
    return {
        "low": _money(low), "central": _money(central), "high": _money(high),
        "offered_price": _money(offered), "difference_from_estimate": _money(offered - central),
        "position": position, "method": "stima_interna_illustrativa",
        "source": "Prezzo nuovo originario indicato, curva illustrativa per età e km; non è una quotazione di mercato",
        "age_years": round(age, 2), "initial_km": round(current_km),
    }


def _loan(vehicle: dict, financing: dict, months: int) -> dict:
    price = _number(vehicle, "purchase_price", "vehicle", 0)
    trade_in = _number(vehicle, "trade_in_value", "vehicle", 0)
    if trade_in > price:
        raise CalculationError("vehicle.trade_in_value", "La permuta non può superare il prezzo dell'auto acquistata.")
    enabled = financing.get("enabled") is True
    if not enabled:
        return {"enabled": False, "principal": 0.0, "ordinary_payment": 0.0,
                "monthly_fee": 0.0, "payments": [0.0] * months,
                "interest": 0.0, "credit_cost": 0.0, "remaining_debt": 0.0,
                "initial_cash": price - trade_in, "term_months": 0, "balloon": 0.0,
                "origination_fee": 0.0, "settlement_fee": 0.0}
    down = _number(financing, "down_payment", "financing", 0)
    principal = _number(financing, "loan_amount", "financing", price - down - trade_in)
    if financing.get("loan_amount") is not None and financing.get("down_payment") is not None and abs(down + principal + trade_in - price) > .01:
        raise CalculationError("financing.down_payment", "Anticipo, prestito e permuta devono sommare al prezzo dell'auto.")
    if principal <= 0 or principal + trade_in > price:
        raise CalculationError("financing.loan_amount", "Il prestito deve essere maggiore di zero e non superare il prezzo dell'auto.")
    term = int(_number(financing, "term_months", "financing", 48, 1, 180))
    tan = _number(financing, "tan_pct", "financing", 0, 0, 60)
    balloon = _number(financing, "balloon", "financing", 0)
    if balloon > principal:
        raise CalculationError("financing.balloon", "La maxi-rata non può superare il capitale finanziato.")
    origination = _number(financing, "origination_fee", "financing", 0)
    monthly_fee = _number(financing, "monthly_fee", "financing", 0)
    settlement = _number(financing, "settlement_fee", "financing", 0)
    rate = tan / 1200
    payment = ((principal - balloon / ((1 + rate) ** term)) * rate / (1 - (1 + rate) ** (-term))) if rate else (principal - balloon) / term
    balance = principal
    payments = []
    interest_paid = 0.0
    for month in range(1, months + 1):
        if month <= term:
            interest = balance * rate
            interest_paid += interest
            balance = balance + interest - payment
            paid = payment + monthly_fee
            if month == term:
                paid += balloon
                balance -= balloon
            balance = max(balance, 0.0)
            payments.append(paid)
        else:
            payments.append(0.0)
    remaining = balance if months < term else 0.0
    settlement_due = settlement if remaining > .01 else 0.0
    credit_cost = interest_paid + origination + monthly_fee * min(months, term) + settlement_due
    return {"enabled": True, "principal": principal, "ordinary_payment": payment,
            "monthly_fee": monthly_fee, "payments": payments,
            "interest": interest_paid, "credit_cost": credit_cost,
            "remaining_debt": remaining, "initial_cash": price - principal - trade_in + origination,
            "term_months": term, "balloon": balloon, "origination_fee": origination,
            "settlement_fee": settlement_due}


def _label(ratio: float | None, margin: float | None, liquidity_ok: bool | None, missing: list[str], adverse_margin: float | None):
    if missing:
        return "dati_insufficienti"
    if margin is not None and margin < 0 or liquidity_ok is False:
        return "non_sostenibile"
    if (ratio is not None and ratio > .30) or (adverse_margin is not None and adverse_margin < 0):
        return "fragile_agli_imprevisti"
    if ratio is not None and ratio > .20:
        return "sostenibile_con_compromessi"
    return "sostenibile_con_margine"


def _core(data: dict, *, months_override=None, insurance_override=None, tyre_override=None,
          residual_override=None, cost_factors=None, income_factor=1.0) -> dict:
    if not isinstance(data, dict):
        raise CalculationError("body", "Invia un oggetto JSON.")
    v = _section(data, "vehicle")
    u = _section(data, "usage")
    insurance = _section(data, "insurance")
    tax = _section(data, "tax")
    tyres = _section(data, "tyres")
    maint = _section(data, "maintenance")
    revision = _section(data, "revision")
    financing = _section(data, "financing")
    budget = _section(data, "budget")
    factors = cost_factors or {}
    purchase_price = _number(v, "purchase_price", "vehicle", None)
    if purchase_price is None or purchase_price <= 0:
        raise CalculationError("vehicle.purchase_price", "Inserisci il prezzo effettivo dell'auto, maggiore di zero.")
    purchase_fees = _number(v, "purchase_fees", "vehicle", 0)
    purchase_date = _date(v, "purchase_date", "vehicle", date.today())
    years = _number(u, "years", "usage", 4, .25, 15)
    months = months_override or int(round(years * 12))
    if not 3 <= months <= 180:
        raise CalculationError("usage.years", "La durata deve essere tra 3 mesi e 15 anni.")
    years = months / 12
    annual_km = _number(u, "annual_km", "usage", None, 0, 200000)
    km_for_math = annual_km if annual_km is not None else 0.0
    estimator_usage = dict(u, annual_km=km_for_math)
    residual = estimate_residual(v, estimator_usage, months, purchase_date)
    if residual_override is not None:
        residual["central"] = residual_override
    fuel = _choice(v, "fuel_type", "vehicle", {"petrol", "diesel", "lpg", "cng", "hybrid", "phev", "electric"}, "petrol")
    insurance_channel = insurance_override or _choice(insurance, "channel", "insurance", {"online", "agency"}, "online")
    tyre_tier = tyre_override or _choice(tyres, "tier", "tyres", {"base", "good"}, "base")
    tyre_type = _choice(tyres, "type", "tyres", {"all_season", "summer", "winter", "seasonal"}, "all_season")
    missing = []
    warnings = []
    assumptions = []
    if annual_km is None:
        missing.append("usage.annual_km")
    if residual["method"] != "manuale":
        warnings.append("Il valore di rivendita è una stima illustrativa interna, non una quotazione aggiornata del mercato.")
    if residual["age_assumed"]:
        warnings.append("Età all'acquisto ipotizzata perché manca la data di immatricolazione.")
        if v.get("condition", "used") in ("used", "owned"):
            missing.append("vehicle.registration_date")
    if residual["method"] == "manuale" and not v.get("residual_source"):
        warnings.append("Indica la fonte e la data del valore residuo inserito manualmente.")
    if v.get("condition") == "owned":
        assumptions.append("Per un'auto già posseduta, il prezzo indicato è trattato come valore vendibile attuale.")
    premium = _number(insurance, f"{insurance_channel}_annual", "insurance", None)
    if premium is None:
        missing.append(f"insurance.{insurance_channel}_annual")
        premium = 0.0
    insurance_increase = _number(insurance, "annual_increase_pct", "insurance", 0, -50, 100) / 100
    tax_annual = _number(tax, "annual", "tax", None)
    if tax_annual is None:
        missing.append("tax.annual")
        tax_annual = 0.0
    super_annual = _number(tax, "super_annual", "tax", 0)
    tax_increase = _number(tax, "annual_increase_pct", "tax", 0, -50, 100) / 100
    tax_due_date = _date(tax, "next_due_date", "tax")
    if tax_due_date is None:
        warnings.append("Scadenza del bollo non indicata: nel calendario si ipotizza il pagamento all'acquisto e poi ogni 12 mesi.")
        tax_due_date = purchase_date
    while tax_due_date < purchase_date:
        tax_due_date = _add_months(tax_due_date, 12)
    # The tax cost is based on actual deadlines within ownership. A due date
    # coinciding with the sale is excluded (the buyer may need to agree who pays).
    tax_schedule = {}
    tax_at_purchase = 0.0
    next_tax_due = tax_due_date
    tax_payment_index = 0
    while next_tax_due < _add_months(purchase_date, months):
        amount = (tax_annual + super_annual) * (1 + tax_increase) ** tax_payment_index
        if next_tax_due == purchase_date:
            tax_at_purchase = amount
        else:
            due_month = next((m for m in range(1, months + 1)
                              if _add_months(purchase_date, m - 1) < next_tax_due <= _add_months(purchase_date, m)), None)
            if due_month is not None:
                tax_schedule[due_month] = tax_schedule.get(due_month, 0) + amount
        next_tax_due = _add_months(next_tax_due, 12)
        tax_payment_index += 1
    consumption = _number(u, "consumption_per_100km", "usage", None)
    energy_price = _number(u, "energy_price", "usage", None)
    electric_consumption = _number(u, "electric_consumption_per_100km", "usage", None)
    electric_price = _number(u, "electric_price", "usage", None)
    efficiency = _number(u, "charging_efficiency", "usage", .90, .5, 1)
    electric_share = _number(u, "electric_share", "usage", 50 if fuel == "phev" else (100 if fuel == "electric" else 0), 0, 100) / 100
    if fuel == "electric":
        electric_share = 1
    if fuel != "electric" and km_for_math > 0 and (consumption is None or energy_price is None):
        missing.extend(k for k, val in (("usage.consumption_per_100km", consumption), ("usage.energy_price", energy_price)) if val is None)
    if fuel in ("electric", "phev") and electric_share > 0 and km_for_math > 0 and (electric_consumption is None or electric_price is None):
        missing.extend(k for k, val in (("usage.electric_consumption_per_100km", electric_consumption), ("usage.electric_price", electric_price)) if val is None)
    annual_fuel = km_for_math / 100 * (1 - electric_share) * (consumption or 0) * (energy_price or 0)
    annual_electric = km_for_math / 100 * electric_share * (electric_consumption or 0) / efficiency * (electric_price or 0)
    fuel_factor = factors.get("fuel", 1.0)
    insurance_factor = factors.get("insurance", 1.0)
    maintenance_factor = factors.get("maintenance", 1.0)
    set_price = _number(tyres, f"{tyre_tier}_set_price", "tyres", None)
    if set_price is None:
        missing.append(f"tyres.{tyre_tier}_set_price")
        set_price = 0.0
    life_km = _number(tyres, "life_km", "tyres", 40000, 1000, 200000)
    life_years = _number(tyres, "life_years", "tyres", 6, 1, 15)
    remaining_km = _number(tyres, "initial_remaining_km", "tyres", life_km, 0)
    remaining_years = _number(tyres, "initial_remaining_years", "tyres", life_years, 0)
    if v.get("condition", "used") in ("used", "km0", "owned"):
        if tyres.get("initial_remaining_km") is None:
            missing.append("tyres.initial_remaining_km")
        if tyres.get("initial_remaining_years") is None:
            missing.append("tyres.initial_remaining_years")
        if maint.get("initial_remaining_service_km") is None:
            missing.append("maintenance.initial_remaining_service_km")
        if maint.get("initial_remaining_service_months") is None:
            missing.append("maintenance.initial_remaining_service_months")
        if any(key.startswith(("tyres.initial", "maintenance.initial")) for key in missing):
            warnings.append("Per un usato verifica lo stato effettivo di gomme e tagliando: i campi vuoti assumono componenti appena sostituiti.")
    change_annual = _number(tyres, "seasonal_change_annual", "tyres", 0)
    storage_annual = _number(tyres, "storage_annual", "tyres", 0)
    tyre_sets = 2 if tyre_type == "seasonal" else 1
    tyre_trackers = [{"km": remaining_km, "months": remaining_years * 12} for _ in range(tyre_sets)]
    service_cost = _number(maint, "service_cost", "maintenance", None)
    if service_cost is None:
        missing.append("maintenance.service_cost")
        service_cost = 0.0
    service_km = _number(maint, "service_interval_km", "maintenance", 15000, 1000)
    service_months = _number(maint, "service_interval_months", "maintenance", 12, 1)
    service_remaining_km = _number(maint, "initial_remaining_service_km", "maintenance", service_km)
    service_remaining_months = _number(maint, "initial_remaining_service_months", "maintenance", service_months)
    repairs_annual = _number(maint, "repairs_annual", "maintenance", None)
    if repairs_annual is None:
        missing.append("maintenance.repairs_annual")
        repairs_annual = 0.0
    other_annual = _number(maint, "other_annual", "maintenance", 0)
    events_input = maint.get("events") or []
    if not isinstance(events_input, list):
        raise CalculationError("maintenance.events", "Deve essere un elenco di interventi.")
    scheduled = {}
    for index, item in enumerate(events_input):
        if not isinstance(item, dict):
            raise CalculationError(f"maintenance.events.{index}", "Intervento non valido.")
        when = _number(item, "year", f"maintenance.events.{index}", None, 0, 15)
        cost = _number(item, "cost", f"maintenance.events.{index}", None)
        if when is None or cost is None:
            raise CalculationError(f"maintenance.events.{index}", "Indica anno e costo dell'intervento.")
        month = max(1, int(round(when * 12)))
        if month <= months:
            scheduled.setdefault(month, []).append({"label": str(item.get("label") or "Intervento"), "cost": cost})
    revision_cost = _number(revision, "cost", "revision", None)
    if revision_cost is None:
        missing.append("revision.cost")
        revision_cost = 0.0
    registration = _date(v, "registration_date", "vehicle")
    last_revision = _date(revision, "last_revision_date", "revision")
    if last_revision and last_revision > purchase_date:
        raise CalculationError("revision.last_revision_date", "La revisione precedente non può essere nel futuro rispetto all'acquisto.")
    if last_revision:
        revision_due = _add_months(last_revision, 24)
        while revision_due <= purchase_date:
            revision_due = _add_months(revision_due, 24)
    elif registration:
        revision_due = _add_months(registration, 48)
        while revision_due <= purchase_date:
            revision_due = _add_months(revision_due, 24)
    elif v.get("condition") == "new":
        revision_due = _add_months(purchase_date, 48)
    else:
        revision_due = None
        missing.append("revision.last_revision_date_or_vehicle.registration_date")
    loan = _loan(v, financing, months)
    categories = ("fuel", "insurance", "tax", "tyres", "service", "revision", "repairs", "other")
    monthly = []
    events = []
    for m in range(1, months + 1):
        year_index = (m - 1) // 12
        costs = {key: 0.0 for key in categories}
        costs["fuel"] = (annual_fuel + annual_electric) * fuel_factor / 12
        costs["insurance"] = premium * insurance_factor * (1 + insurance_increase) ** year_index if (m - 1) % 12 == 0 else 0.0
        costs["tax"] = (tax_at_purchase if m == 1 else 0.0) + tax_schedule.get(m, 0.0)
        costs["repairs"] = repairs_annual * maintenance_factor / 12
        costs["other"] = other_annual / 12
        if tyre_type == "seasonal":
            costs["tyres"] += (change_annual + storage_annual) / 12
        for tracker in tyre_trackers:
            tracker["km"] -= km_for_math / 12 / tyre_sets
            tracker["months"] -= 1
            tyre_count = 0
            while tracker["km"] <= 0 or tracker["months"] <= 0:
                costs["tyres"] += set_price
                tracker["km"] = tracker["km"] + life_km if tracker["km"] <= 0 else life_km
                tracker["months"] = tracker["months"] + life_years * 12 if tracker["months"] <= 0 else life_years * 12
                events.append({"month": m, "year": year_index + 1, "type": "tyres", "label": "Sostituzione pneumatici", "cost": _money(set_price)})
                tyre_count += 1
                if tyre_count > 20:
                    raise CalculationError("usage.annual_km", "Percorrenza incompatibile con la durata dei pneumatici.")
        service_remaining_km -= km_for_math / 12
        service_remaining_months -= 1
        service_count = 0
        while service_remaining_km <= 0 or service_remaining_months <= 0:
            costs["service"] += service_cost * maintenance_factor
            events.append({"month": m, "year": year_index + 1, "type": "service", "label": "Tagliando", "cost": _money(service_cost * maintenance_factor)})
            service_remaining_km = service_remaining_km + service_km if service_remaining_km <= 0 else service_km
            service_remaining_months = service_remaining_months + service_months if service_remaining_months <= 0 else service_months
            service_count += 1
            if service_count > 20:
                raise CalculationError("usage.annual_km", "Percorrenza incompatibile con l'intervallo dei tagliandi.")
        for event in scheduled.get(m, []):
            costs["service"] += event["cost"] * maintenance_factor
            events.append({"month": m, "year": year_index + 1, "type": "maintenance", "label": event["label"], "cost": _money(event["cost"] * maintenance_factor)})
        end_of_month = _add_months(purchase_date, m)
        start_of_month = _add_months(purchase_date, m - 1)
        while revision_due and start_of_month < revision_due <= end_of_month:
            costs["revision"] += revision_cost
            events.append({"month": m, "year": year_index + 1, "type": "revision", "label": "Revisione", "cost": _money(revision_cost), "due_date": revision_due.isoformat()})
            revision_due = _add_months(revision_due, 24)
        monthly.append({"costs": costs, "loan_payment": loan["payments"][m - 1]})
    totals = {key: sum(month["costs"][key] for month in monthly) for key in categories}
    management = sum(totals.values())
    depreciation = purchase_price - residual["central"]
    credit_cost = loan["credit_cost"]
    total_cost = depreciation + purchase_fees + management + credit_cost
    monthly_cost = total_cost / months
    insurance_at_purchase = premium * insurance_factor
    initial_cash = loan["initial_cash"] + purchase_fees + insurance_at_purchase + tax_at_purchase
    sale_equity = residual["central"] - loan["remaining_debt"]
    budget_income = _number(budget, "net_monthly_income", "budget", None)
    income_ordinary = budget_income * income_factor if budget_income is not None else None
    payments_per_year = int(_number(budget, "annual_payments", "budget", 12, 12, 14))
    income_avg = income_ordinary * payments_per_year / 12 if income_ordinary is not None else None
    other_expenses = _number(budget, "other_monthly_expenses", "budget", None)
    savings = _number(budget, "min_monthly_savings", "budget", 0)
    available_cash = _number(budget, "available_cash", "budget", None)
    emergency_reserve = _number(budget, "emergency_reserve", "budget", 0)
    emergency_months = _number(budget, "emergency_months", "budget", 3, 0, 24)
    if income_ordinary is None:
        missing.append("budget.net_monthly_income")
    if other_expenses is None:
        missing.append("budget.other_monthly_expenses")
    if available_cash is None:
        missing.append("budget.available_cash")
    regular_payment = (loan["ordinary_payment"] + loan["monthly_fee"]) if loan["enabled"] else 0.0
    cash_monthly = regular_payment + management / months
    cash_monthly_average = sum(loan["payments"]) / months + management / months
    cash_monthly_after_loan = management / months
    monthly_margin = income_ordinary - (other_expenses or 0) - cash_monthly - savings if income_ordinary is not None and other_expenses is not None else None
    liquidity_remaining = available_cash - initial_cash if available_cash is not None else None
    reserve_required = max(emergency_reserve, (other_expenses or 0) * emergency_months)
    liquidity_ok = liquidity_remaining >= reserve_required if liquidity_remaining is not None and other_expenses is not None else None
    target_replacement = _number(budget, "target_replacement_price", "budget", None)
    replacement_fund = _number(budget, "replacement_fund", "budget", 0)
    replacement_monthly = max(0, (target_replacement - sale_equity - replacement_fund) / months) if target_replacement is not None else None
    cash_calendar = [{"month": 0, "date": purchase_date.isoformat(),
                      "purchase_cash": _money(loan["initial_cash"] + purchase_fees),
                      "trade_in_value": _money(_number(v, "trade_in_value", "vehicle", 0)),
                      "insurance_bill": _money(insurance_at_purchase), "tax_bill": _money(tax_at_purchase),
                      "outflow": _money(initial_cash), "sale_proceeds": 0, "loan_payoff": 0,
                      "net_cash_flow": _money(-initial_cash)}]
    for m, row in enumerate(monthly, start=1):
        year_index = (m - 1) // 12
        costs = row["costs"]
        # Tax and insurance are modelled as anniversary payments; planned repairs
        # remain a reserve rather than a bill that has certainly occurred.
        insurance_bill = premium * insurance_factor * (1 + insurance_increase) ** (m // 12) if m % 12 == 0 and m < months else 0
        tax_bill = tax_schedule.get(m, 0)
        outflow = sum(costs[key] for key in ("fuel", "tyres", "service", "revision", "other")) + insurance_bill + tax_bill + row["loan_payment"]
        sale_proceeds = residual["central"] if m == months else 0
        loan_payoff = loan["remaining_debt"] + loan["settlement_fee"] if m == months else 0
        outflow += loan_payoff
        cash_calendar.append({"month": m, "date": _add_months(purchase_date, m).isoformat(),
                              "outflow": _money(outflow), "planned_repair_reserve": _money(costs["repairs"]),
                              "insurance_bill": _money(insurance_bill), "tax_bill": _money(tax_bill),
                              "loan_payment": _money(row["loan_payment"]),
                              "sale_proceeds": _money(sale_proceeds), "loan_payoff": _money(loan_payoff),
                              "net_cash_flow": _money(sale_proceeds - outflow)})
    annual = []
    for year in range((months + 11) // 12):
        rows = monthly[year * 12:(year + 1) * 12]
        annual_breakdown = {key: _money(sum(row["costs"][key] for row in rows)) for key in categories}
        annual_management = sum(annual_breakdown.values())
        payments = sum(row["loan_payment"] for row in rows)
        annual_cash_rows = cash_calendar[year * 12 + 1:(year + 1) * 12 + 1]
        if year == 0:
            annual_cash_rows = [cash_calendar[0], *annual_cash_rows]
        annual.append({"year": year + 1, "months": len(rows), "km": round(km_for_math * len(rows) / 12),
                       "breakdown": annual_breakdown, "management_total": _money(annual_management),
                       "loan_payments": _money(payments),
                       "budget_requirement": _money(annual_management + payments),
                       "cash_outflow": _money(sum(x["outflow"] for x in annual_cash_rows)),
                       "planned_repair_reserve": _money(sum(x.get("planned_repair_reserve", 0) for x in annual_cash_rows))})
    economic_ratio = monthly_cost / income_avg if income_avg and income_avg > 0 else None
    cash_ratio = cash_monthly / income_ordinary if income_ordinary and income_ordinary > 0 else None
    if income_ordinary == 0:
        missing.append("budget.net_monthly_income_positive")
    breakdown = {
        "depreciation": _money(depreciation), "purchase_fees": _money(purchase_fees),
        "credit_cost": _money(credit_cost), **{key: _money(value) for key, value in totals.items()},
    }
    summary = {
        "total_cost": _money(total_cost), "monthly_cost": _money(monthly_cost),
        "cost_per_km": _money(total_cost / (km_for_math * years)) if km_for_math > 0 else None,
        "management_total": _money(management), "depreciation": _money(depreciation),
        "credit_cost": _money(credit_cost), "cash_monthly": _money(cash_monthly),
        "cash_monthly_average": _money(cash_monthly_average),
        "cash_monthly_after_loan": _money(cash_monthly_after_loan),
        "initial_cash": _money(initial_cash), "final_km": round(residual["final_km"]),
        "trade_in_value": _money(_number(v, "trade_in_value", "vehicle", 0)),
        "age_at_sale": round(residual["age_at_sale"], 2),
        "residual_value": _money(residual["central"]),
        "residual_value_low": _money(residual["low"]),
        "residual_value_high": _money(residual["high"]),
        "residual_method": residual["method"], "residual_source": residual["source"],
        "remaining_debt": _money(loan["remaining_debt"]), "sale_equity": _money(sale_equity),
        "regular_loan_payment": _money(regular_payment),
        "loan_balloon": _money(loan["balloon"]), "loan_term_months": loan["term_months"],
        "peak_year_cash_monthly": _money(max(row["cash_outflow"] / row["months"] for row in annual)),
        "economic_income_ratio": _fraction(economic_ratio), "cash_income_ratio": _fraction(cash_ratio),
        "monthly_margin": _money(monthly_margin), "liquidity_remaining": _money(liquidity_remaining),
        "emergency_reserve_required": _money(reserve_required),
        "replacement_monthly": _money(replacement_monthly),
        "affordability_label": None, "missing_data": sorted(set(missing)),
        "years": years, "months": months,
    }
    if residual["central"] < loan["remaining_debt"]:
        warnings.append("Alla vendita il valore stimato non copre il debito residuo.")
    if loan["enabled"] and loan["balloon"] > 0:
        warnings.append("La maxi-rata richiede liquidità alla scadenza; verifica il calendario dei pagamenti.")
    if other_expenses is not None and available_cash is not None and liquidity_ok is False:
        warnings.append("Dopo l'esborso iniziale la liquidità è inferiore alla riserva impostata.")
    assumptions.extend([
        "Importi futuri a prezzi costanti, salvo aumenti annuali inseriti per bollo e assicurazione.",
        "Premi assicurativi online e agenzia devono riferirsi alle stesse coperture.",
        "Il costo economico include svalutazione e soli costi del credito; le rate figurano nella cassa.",
        "cash_monthly è l'impegno durante il prestito; cash_monthly_average è la media del possesso. Il calendario include acquisto, pagamento del debito e vendita.",
        "Liquidità iniziale e quota mensile di gestione sono due viste dello stesso budget: la prima polizza e il primo bollo figurano in entrambe, quindi non vanno sommati come costi aggiuntivi.",
        "Assicurazione iniziale pagata all'acquisto, rinnovi ogni 12 mesi; bollo secondo la scadenza indicata o l'ipotesi all'acquisto.",
        "Le riparazioni future sono una riserva stimata: compaiono nel budget economico ma non come fatture certe nel calendario di cassa.",
        "La cassa del primo anno comprende l'esborso iniziale; il bollo coincidente con la vendita non è addebitato.",
        "Carburante in litri/100 km o energia in kWh/100 km; per GPL/metano usare unità e prezzo coerenti.",
    ])
    return {"summary": summary, "breakdown": breakdown, "annual": annual,
            "cash_calendar": cash_calendar,
            "events": events, "assumptions": assumptions, "warnings": warnings,
            "_income_ordinary": income_ordinary, "_other_expenses": other_expenses,
            "_savings": savings, "_liquidity_ok": liquidity_ok}


def calculate_evaluation(data: dict) -> dict:
    """Calculate a full report, including scenarios and comparable choices."""
    base = _core(data)
    s = base["summary"]
    vehicle = _section(data, "vehicle")
    purchase_date = _date(vehicle, "purchase_date", "vehicle", date.today())
    base["purchase_estimate"] = estimate_purchase_price(vehicle, purchase_date)
    if vehicle.get("condition", "used") in ("used", "km0"):
        if base["purchase_estimate"] is None:
            base["warnings"].append("Per confrontare il prezzo richiesto con una stima interna servono prezzo nuovo originario, immatricolazione e km attuali. Il confronto è facoltativo.")
        else:
            base["warnings"].append("Il confronto con il prezzo richiesto usa una curva illustrativa, non annunci o quotazioni aggiornate.")
    scenario_input = _section(data, "scenarios")
    fuel_up = _number(scenario_input, "fuel_increase_pct", "scenarios", 20, 0, 200) / 100
    insurance_up = _number(scenario_input, "insurance_increase_pct", "scenarios", 20, 0, 200) / 100
    maintenance_up = _number(scenario_input, "maintenance_increase_pct", "scenarios", 30, 0, 200) / 100
    residual_down = _number(scenario_input, "residual_drop_pct", "scenarios", 20, 0, 90) / 100
    income_down = _number(scenario_input, "income_drop_pct", "scenarios", 10, 0, 90) / 100
    extra_repair = _number(scenario_input, "extra_repair", "scenarios", 0)
    prudent_residual = _number(vehicle, "residual_value_low", "vehicle", None)
    if prudent_residual is None:
        prudent_residual = s["residual_value_low"]
    prudent = _core(data, residual_override=prudent_residual,
                    cost_factors={"fuel": 1 + fuel_up, "insurance": 1 + insurance_up,
                                  "maintenance": 1 + maintenance_up})
    adverse = _core(data, residual_override=prudent_residual, income_factor=1 - income_down,
                    cost_factors={"fuel": 1 + fuel_up, "insurance": 1 + insurance_up,
                                  "maintenance": 1 + maintenance_up})
    if extra_repair:
        adverse["summary"]["total_cost"] = _money(adverse["summary"]["total_cost"] + extra_repair)
        adverse["summary"]["monthly_cost"] = _money(adverse["summary"]["total_cost"] / s["months"])
        adverse["summary"]["cash_monthly"] = _money(adverse["summary"]["cash_monthly"] + extra_repair / s["months"])
        if adverse["summary"]["monthly_margin"] is not None:
            adverse["summary"]["monthly_margin"] = _money(adverse["summary"]["monthly_margin"] - extra_repair / s["months"])
    # The explicit residual-drop parameter may be more severe than the low estimate.
    shock_residual = s["residual_value"] * (1 - residual_down)
    if shock_residual < adverse["summary"]["residual_value"]:
        delta = adverse["summary"]["residual_value"] - shock_residual
        adverse["summary"]["residual_value"] = _money(shock_residual)
        adverse["summary"]["total_cost"] = _money(adverse["summary"]["total_cost"] + delta)
        adverse["summary"]["monthly_cost"] = _money(adverse["summary"]["total_cost"] / s["months"])
        adverse["summary"]["sale_equity"] = _money(shock_residual - adverse["summary"]["remaining_debt"])
    s["affordability_label"] = _label(s["economic_income_ratio"], s["monthly_margin"],
                                    base["_liquidity_ok"], s["missing_data"], adverse["summary"]["monthly_margin"])
    insurance_comparison = {}
    for channel in ("online", "agency"):
        if _section(data, "insurance").get(f"{channel}_annual") is not None:
            x = _core(data, insurance_override=channel)["summary"]
            insurance_comparison[channel] = {"monthly_cost": x["monthly_cost"], "difference_from_selected": _money(x["monthly_cost"] - s["monthly_cost"])}
    tyre_comparison = {}
    for tier in ("base", "good"):
        if _section(data, "tyres").get(f"{tier}_set_price") is not None:
            x = _core(data, tyre_override=tier)["summary"]
            tyre_comparison[tier] = {"monthly_cost": x["monthly_cost"], "difference_from_selected": _money(x["monthly_cost"] - s["monthly_cost"])}
    duration_comparison = []
    for years in (3, 4, 5, 6, 8, 10):
        # A manual residual is valid for the chosen horizon only. For other horizons,
        # use the illustrative estimator and label the result accordingly.
        altered = deepcopy(data)
        altered_vehicle = _section(altered, "vehicle")
        altered_vehicle.pop("residual_value", None)
        altered_vehicle.pop("residual_value_low", None)
        altered_vehicle.pop("residual_value_high", None)
        d = _core(altered, months_override=years * 12)["summary"]
        duration_comparison.append({"years": years, "monthly_cost": d["monthly_cost"],
                                    "total_cost": d["total_cost"], "residual_value": d["residual_value"],
                                    "method": d["residual_method"]})
    base.pop("_income_ordinary")
    base.pop("_other_expenses")
    base.pop("_savings")
    base.pop("_liquidity_ok")
    base["scenarios"] = {
        "central": {"monthly_cost": s["monthly_cost"], "total_cost": s["total_cost"], "monthly_margin": s["monthly_margin"], "residual_value": s["residual_value"]},
        "prudent": {key: prudent["summary"][key] for key in ("monthly_cost", "total_cost", "monthly_margin", "residual_value")},
        "adverse": {key: adverse["summary"][key] for key in ("monthly_cost", "total_cost", "monthly_margin", "residual_value")},
    }
    base["comparisons"] = {"insurance": insurance_comparison, "tyres": tyre_comparison,
                           "durations": duration_comparison}
    return base
