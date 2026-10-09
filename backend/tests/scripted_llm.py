"""A model that answers from a script: each call goes to `answer(system, user)`, whose dict is the reply."""
from collections.abc import Callable


class ScriptedLlm:
    def __init__(self, answer: Callable[[str, str], dict], model: str = "big"):
        self.answer, self.model, self.prompts = answer, model, []

    max_output_tokens = None
    cap = 32768

    @property
    def base(self):
        return 8192

    def with_start(self, limit):
        return self

    def start_log(self):
        pass

    def take_log(self):
        return []

    def complete_json(self, system, user, schema):
        self.prompts.append(user)
        out = self.answer(system, user)
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out)

    def start_usage(self):
        pass

    def take_usage(self):
        return None

    def ping(self):
        return True
