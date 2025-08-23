try:
    import openai as _openai

    if not hasattr(_openai, "OpenAIError"):

        class OpenAIError(Exception):
            pass

        _openai.OpenAIError = OpenAIError
except Exception:
    # If openai is not installed, ignore. This shim is optional.
    pass
