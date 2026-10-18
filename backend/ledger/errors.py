class LedgerError(Exception):
    """The only domain exception; `code` is the machine-readable reason."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)
