class MusicError(Exception):
    pass


class NoActiveDevice(MusicError):
    pass


class AuthExpired(MusicError):
    pass


class RateLimited(MusicError):
    pass


class DisambiguationRequired(MusicError):
    pass


class NotFound(MusicError):
    pass


class PolicyRejected(MusicError):
    pass


