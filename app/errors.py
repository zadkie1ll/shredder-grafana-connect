class ServiceError(Exception):
    """Base expected service error."""


class PanelAPIError(ServiceError):
    pass


class PanelAuthenticationError(PanelAPIError):
    pass


class PanelResponseError(PanelAPIError):
    pass


class NotesParseError(ServiceError):
    pass


class SSHConnectionError(ServiceError):
    pass


class SSHAuthenticationError(SSHConnectionError):
    pass


class SSHHostKeyError(SSHConnectionError):
    pass


class NodeExporterInstallError(ServiceError):
    pass


class NodeExporterVerificationError(ServiceError):
    pass


class PrometheusTargetsWriteError(ServiceError):
    pass
