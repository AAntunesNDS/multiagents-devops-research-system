class RetryableError(Exception):
    """Falha transitoria: a state machine deve tentar novamente com backoff."""


class FatalError(Exception):
    """Falha definitiva: aciona o Catch e o fluxo de rollback."""


class NotReadyError(Exception):
    """Recurso ainda em estado de transicao (ex.: NAT em 'pending')."""
