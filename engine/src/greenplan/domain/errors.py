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
