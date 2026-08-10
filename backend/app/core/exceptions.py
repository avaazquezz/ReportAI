from fastapi import HTTPException, status


class ReportAIException(HTTPException):
    """Base for all typed application exceptions. Routers raise these, never a raw HTTPException."""


class AuthenticationException(ReportAIException):
    def __init__(self, detail: str = "Could not validate credentials") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class AuthorizationException(ReportAIException):
    def __init__(self, detail: str = "Not authorized to perform this action") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ResourceNotFoundException(ReportAIException):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ConflictException(ReportAIException):
    def __init__(self, detail: str = "Resource conflict") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ValidationException(ReportAIException):
    def __init__(self, detail: str = "Invalid request") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
