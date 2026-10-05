"""LLM 统一异常类"""
class LLMUnionBaseError(Exception):
    pass

class ModelNotFoundError(LLMUnionBaseError):
    pass

class APIRequestError(LLMUnionBaseError):
    pass

class RateLimitError(LLMUnionBaseError):
    pass

class AuthenticationError(LLMUnionBaseError):
    pass
