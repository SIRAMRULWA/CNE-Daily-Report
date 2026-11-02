"""Application errors translated by HTTP, CLI, and worker entrypoints."""


class ReportDeliveryError(Exception):
    pass


class ReportDeliveryValidationError(ReportDeliveryError):
    pass


class ReportDeliveryConflictError(ReportDeliveryError):
    pass


class ReportDeliveryNotFoundError(ReportDeliveryError):
    pass


class ReportDeliveryProviderError(ReportDeliveryError):
    pass

