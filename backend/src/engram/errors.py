class PermanentError(Exception):
    """A failure that retrying will not fix, such as missing credentials. Jobs that raise it
    fail immediately instead of using up their remaining attempts."""
