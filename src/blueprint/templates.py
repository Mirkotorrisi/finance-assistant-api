"""Starter blueprints. Labels exist in Italian and English; keys are stable, language-neutral ids.

A template is a starting point to adapt (in chat or in the editor), never a fixed taxonomy.
"""

from typing import Any, Dict, List, Tuple

from src.blueprint.schema import Blueprint

LOCALES = ("it", "en")
DEFAULT_LOCALE = "it"

# (italian, english)
L = Tuple[str, str]


def _cat(key: str, label: L, children: List[Dict[str, Any]] | None = None, kind: str = "expense", **attributes: Any) -> Dict[str, Any]:
    return {"key": key, "label": label, "kind": kind, "children": children or [], "attributes": attributes}


def _group(key: str, label: L, members: List[str]) -> Dict[str, Any]:
    return {"key": key, "label": label, "members": members}


_INCOME = _cat("income", ("Entrate", "Income"), [
    _cat("salary", ("Stipendio", "Salary"), kind="income"),
    _cat("other_income", ("Altre entrate", "Other income"), kind="income"),
], kind="income")

_PERSONAL_CATEGORIES = [
    _cat("home", ("Casa", "Home"), [
        _cat("rent_mortgage", ("Affitto / mutuo", "Rent / mortgage")),
        _cat("utilities", ("Utenze", "Utilities")),
        _cat("home_maintenance", ("Manutenzione casa", "Home maintenance")),
    ]),
    _cat("food", ("Alimentari", "Food"), [_cat("groceries", ("Spesa", "Groceries"))]),
    _cat("transport", ("Trasporti", "Transport"), [
        _cat("fuel", ("Carburante", "Fuel")),
        _cat("public_transport", ("Mezzi pubblici", "Public transport")),
        _cat("car", ("Auto (assicurazione, bollo, manutenzione)", "Car (insurance, tax, maintenance)")),
    ]),
    _cat("health", ("Salute", "Health")),
    _cat("leisure", ("Svago", "Leisure"), [
        _cat("dining_out", ("Ristoranti e bar", "Restaurants and bars")),
        _cat("subscriptions", ("Abbonamenti", "Subscriptions")),
        _cat("shopping", ("Shopping", "Shopping")),
        _cat("travel", ("Viaggi", "Travel")),
    ]),
    _cat("savings", ("Risparmio e investimenti", "Savings and investments")),
    _INCOME,
]

_PERSONAL_GROUPS = [
    _group("essentials", ("Essenziali", "Essentials"), ["home", "food", "transport", "health"]),
    _group("discretionary", ("Minchiate", "Discretionary"), ["leisure"]),
]

_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "personal": {
        "name": ("Budget personale", "Personal budget"),
        "description": ("Spese di tutti i giorni divise in essenziali e minchiate.", "Everyday spending split into essentials and discretionary."),
        "instructions": (
            "Spese discrezionali: ristoranti, abbonamenti, shopping e viaggi. Il resto è essenziale.",
            "Discretionary spending: dining out, subscriptions, shopping and travel. Everything else is essential.",
        ),
        "categories": _PERSONAL_CATEGORIES,
        "groups": _PERSONAL_GROUPS,
        "dimensions": [],
        "reports": [{"key": "discretionary_spending", "label": ("Le minchiate", "Discretionary spending"), "group": "discretionary"}],
    },
    "family": {
        "name": ("Famiglia", "Family"),
        "description": ("Budget di famiglia con le spese dei figli separate da quelle della casa.", "Family budget with the children's costs kept apart from the household's."),
        "instructions": (
            "Pannolini, scuola, pediatra, giochi e attività sportive sono spese dei figli, anche se comprate al supermercato o online.",
            "Nappies, school, paediatrician, toys and sports are the children's costs, even when bought at the supermarket or online.",
        ),
        "categories": _PERSONAL_CATEGORIES[:-1] + [
            _cat("children", ("Figli", "Children"), [
                _cat("school", ("Scuola e nido", "School and nursery")),
                _cat("kids_sports", ("Sport e attività", "Sports and activities")),
                _cat("kids_health", ("Salute dei figli", "Children's health")),
                _cat("kids_goods", ("Abbigliamento, giochi e pannolini", "Clothes, toys and nappies")),
            ]),
            _INCOME,
        ],
        "groups": _PERSONAL_GROUPS + [_group("kids", ("Spese dei figli", "Children's costs"), ["children"])],
        "dimensions": [
            {"key": "for_whom", "label": ("Per chi", "For whom"), "values": [
                {"key": "adults", "label": ("Adulti", "Adults")},
                {"key": "children", "label": ("Figli", "Children")},
                {"key": "household", "label": ("Casa", "Household")},
            ]},
        ],
        "reports": [
            {"key": "kids_costs", "label": ("Spese dei figli", "Children's costs"), "group": "kids"},
            {"key": "discretionary_spending", "label": ("Le minchiate", "Discretionary spending"), "group": "discretionary"},
        ],
    },
    "freelancer": {
        "name": ("Libero professionista", "Freelancer"),
        "description": ("Spese dell'attività (deducibili) separate da quelle personali.", "Business (deductible) costs kept apart from personal ones."),
        "instructions": (
            "Le categorie con attributo deductible=true sono spese professionali. Le spese personali non sono deducibili. Nel dubbio chiedi.",
            "Categories with attribute deductible=true are business costs. Personal spending is not deductible. When unsure, ask.",
        ),
        "categories": [
            _cat("office", ("Spese d'ufficio", "Office costs"), [
                _cat("software", ("Software e abbonamenti", "Software and subscriptions"), deductible=True),
                _cat("hardware", ("Computer e attrezzatura", "Computers and equipment"), deductible=True),
                _cat("stationery", ("Cancelleria e materiali", "Stationery and supplies"), deductible=True),
                _cat("coworking", ("Coworking e affitto studio", "Coworking and studio rent"), deductible=True),
            ], deductible=True),
            _cat("client_entertainment", ("Spese di rappresentanza", "Client entertainment"), deductible=True, limited=True),
            _cat("materials", ("Materie prime e materiali di consumo", "Materials and consumables"), deductible=True),
            _cat("business_travel", ("Viaggi e trasferte di lavoro", "Business travel"), deductible=True),
            _cat("training", ("Formazione", "Training"), deductible=True),
            _cat("accountant", ("Commercialista e consulenze", "Accountant and advisers"), deductible=True),
            _cat("taxes_contributions", ("Tasse e contributi", "Taxes and contributions")),
            _cat("personal", ("Spese personali", "Personal spending"), [
                _cat("personal_living", ("Vita quotidiana", "Day-to-day living"), deductible=False),
            ], deductible=False),
            _cat("client_income", ("Incassi da clienti", "Client income"), kind="income"),
        ],
        "groups": [
            _group("business", ("Attività", "Business"), ["office", "client_entertainment", "materials", "business_travel", "training", "accountant"]),
            _group("personal_group", ("Personale", "Personal"), ["personal"]),
        ],
        "dimensions": [],
        "reports": [{"key": "business_costs", "label": ("Costi dell'attività", "Business costs"), "group": "business"}],
    },
    "small_business": {
        "name": ("Piccola azienda", "Small business"),
        "description": ("Costi fissi e variabili, ricavi e imposte di una piccola impresa.", "Fixed and variable costs, revenue and taxes of a small company."),
        "instructions": (
            "Costi variabili: materie prime e logistica. Costi fissi: personale, sede, ufficio e oneri finanziari.",
            "Variable costs: raw materials and logistics. Fixed costs: payroll, premises, office and financial charges.",
        ),
        "categories": [
            _cat("revenue", ("Ricavi", "Revenue"), [
                _cat("sales", ("Vendite", "Sales"), kind="income"),
                _cat("services", ("Servizi", "Services"), kind="income"),
            ], kind="income"),
            _cat("raw_materials", ("Materie prime", "Raw materials"), deductible=True),
            _cat("logistics", ("Trasporti e logistica", "Transport and logistics"), deductible=True),
            _cat("payroll", ("Personale", "Payroll"), deductible=True),
            _cat("premises", ("Sede, affitto e utenze", "Premises, rent and utilities"), deductible=True),
            _cat("marketing", ("Marketing e pubblicità", "Marketing and advertising"), deductible=True),
            _cat("office", ("Ufficio e cancelleria", "Office and supplies"), deductible=True),
            _cat("client_entertainment", ("Spese di rappresentanza", "Client entertainment"), deductible=True, limited=True),
            _cat("financial", ("Oneri bancari e finanziari", "Bank and financial charges"), deductible=True),
            _cat("equipment", ("Investimenti e attrezzature", "Equipment and investments")),
            _cat("taxes", ("Imposte e tasse", "Taxes")),
        ],
        "groups": [
            _group("variable_costs", ("Costi variabili", "Variable costs"), ["raw_materials", "logistics"]),
            _group("fixed_costs", ("Costi fissi", "Fixed costs"), ["payroll", "premises", "office", "financial"]),
        ],
        "dimensions": [],
        "reports": [
            {"key": "variable", "label": ("Costi variabili", "Variable costs"), "group": "variable_costs"},
            {"key": "fixed", "label": ("Costi fissi", "Fixed costs"), "group": "fixed_costs"},
        ],
    },
}


def _localize(value: Any, index: int) -> Any:
    """Pick the language of every (it, en) pair, recursively."""
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, str) for v in value):
        return value[index]
    if isinstance(value, list):
        return [_localize(v, index) for v in value]
    if isinstance(value, dict):
        return {k: _localize(v, index) for k, v in value.items()}
    return value


def list_templates(locale: str = DEFAULT_LOCALE) -> List[Dict[str, str]]:
    index = LOCALES.index(locale) if locale in LOCALES else 0
    return [
        {"key": key, "name": t["name"][index], "description": t["description"][index]}
        for key, t in _TEMPLATES.items()
    ]


def build_template(key: str, locale: str = DEFAULT_LOCALE) -> Blueprint:
    if key not in _TEMPLATES:
        raise KeyError(key)
    index = LOCALES.index(locale) if locale in LOCALES else 0
    data = _localize(_TEMPLATES[key], index)
    return Blueprint.model_validate(data)
