class GreenPlanError(Exception):
    pass


class ConversionError(GreenPlanError):
    pass


class DrawingLoadError(GreenPlanError):
    pass


class KnowledgeValidationError(GreenPlanError):
    pass


class ConfigurationError(GreenPlanError):
    pass


class ExportError(GreenPlanError):
    pass


class InvalidUploadError(GreenPlanError):
    pass


class JobNotFoundError(GreenPlanError):
    pass
