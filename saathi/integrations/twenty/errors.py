"""Fail-closed Twenty integration errors without secret-bearing payloads."""


class TwentyError(RuntimeError):
    """Base error safe for normalization by the connector runtime."""


class TwentyConfigurationError(TwentyError):
    pass


class TwentyContractError(TwentyError):
    pass


class TwentyTransportError(TwentyError):
    pass


class TwentyReadOnlyViolation(TwentyError):
    pass


class TwentyScopeViolation(TwentyError):
    pass


class TwentyWebhookRejected(TwentyError):
    pass
