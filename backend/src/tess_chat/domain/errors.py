class DomainError(Exception):
    code = "domain_error"


class NotFound(DomainError):
    code = "not_found"


class Forbidden(DomainError):
    code = "forbidden"


class InvalidInput(DomainError):
    code = "invalid_input"


class InsufficientCredits(DomainError):
    code = "insufficient_credits"


class LLMUnavailable(DomainError):
    code = "llm_unavailable"
