import re


INTENT_TERMS = {
    "human_handoff": ("atendente", "humano", "pessoa", "gerente", "reclamação"),
    "sales": ("comprar", "preço", "valor", "orçamento", "plano", "produto", "serviço", "contratar"),
    "scheduling": ("agendar", "agenda", "horário", "marcar", "consulta", "visita"),
    "order_status": ("pedido", "entrega", "rastreio", "rastrear", "encomenda"),
    "support": ("problema", "erro", "ajuda", "suporte", "não funciona", "troca", "devolução"),
}


def classify_intent(text: str) -> tuple[str, float]:
    lowered = text.casefold()
    scored = {intent: sum(term in lowered for term in terms) for intent, terms in INTENT_TERMS.items()}
    intent, hits = max(scored.items(), key=lambda item: item[1])
    if not hits:
        return "general", 0.35
    return intent, min(0.55 + hits * 0.15, 0.95)


def detect_language(text: str, fallback: str = "pt-BR") -> str:
    lowered = f" {text.casefold()} "
    scores = {
        "pt-BR": sum(word in lowered for word in (" você ", " não ", " para ", " preço ", " olá ", " obrigado ")),
        "es": sum(word in lowered for word in (" usted ", " para ", " precio ", " hola ", " gracias ", " quiero ")),
        "en": sum(word in lowered for word in (" you ", " the ", " price ", " hello ", " thanks ", " want ")),
    }
    language, score = max(scores.items(), key=lambda item: item[1])
    return language if score else fallback


def detect_sentiment(text: str) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("péssimo", "absurdo", "irritado", "raiva", "processo", "denúncia")):
        return "negative"
    if any(term in lowered for term in ("obrigado", "perfeito", "ótimo", "excelente", "adorei")):
        return "positive"
    return "neutral"


def extract_profile(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    email = re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text)
    phone = re.search(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)", text)
    name = re.search(r"(?:meu nome (?:é|e)|me chamo|sou o|sou a)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ '\-]{1,50})", text, re.I)
    budget = re.search(r"(?:orçamento|budget|até|disponho de)\s*(?:de\s*)?(R\$\s*[\d.,]+)", text, re.I)
    if email:
        fields["email"] = email.group(0)
    if phone:
        fields["phone"] = phone.group(0).strip()
    if name:
        fields["name"] = name.group(1).strip(" .,!")
    if budget:
        fields["budget"] = budget.group(1)
    return fields


def missing_lead_fields(configured_fields: list[dict], profile: dict) -> list[dict]:
    return [field for field in configured_fields if field.get("required", True) and not profile.get(field["name"])]
