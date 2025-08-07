import openai

if not hasattr(openai, "OpenAIError"):

    class OpenAIError(Exception):
        pass

    openai.OpenAIError = OpenAIError
