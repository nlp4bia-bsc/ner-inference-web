class ServiceError(Exception):
    def __init__(self, message: str, status: int = 422, retry_after: int | None = None):
        self.message = message
        self.status = status
        self.retry_after = retry_after
        super().__init__(message)
