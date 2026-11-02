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


def intro_answer(user: str) -> dict:
    """A passing introduction for any intro prompt (spec 2026-10-09-review-introduction §4.3): every thread introduced
    citing its first story, the route in the threads' order."""
    import re
    body = user.split("THREAD DETAILS (id", 1)[1].split("CONNECTIONS (a", 1)[0]
    rows = re.findall(r"^(T\d+) \| ", body, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n(?:  (?:modules|files): .*\n)*  stories: (S\d+) ", body, re.M))
    return {"whole": "The change reworks the UART driver. It spans the driver and the code that calls it. Each thread "
                     "below says what it adds. The main risk is a caller that misses a new result.",
            "whole_cites": rows[:1],
            "threads": [{"id": t, "intro": f"This thread holds {first.get(t, t)} and what builds on it. Its code sits in "
                                           "the driver. Its open checks say what to confirm.",
                         "cites": [first.get(t, t)]} for t in rows],
            "route": [{"thread": t, "reason": "This thread comes next in the change.", "skim": False, "cites": [t]}
                      for t in rows]}


def design_answer(user: str) -> dict:
    """A passing design text for any design prompt (spec 2026-11-02 §10): the verdict names the first check, one concern
    and one ownership line cite the first story, and every walk-through and condition is named."""
    import re
    causes = re.findall(r"^(c[0-9a-f]{10}) \| ", user, re.M)
    first = re.search(r"^  stories: (S\d+) ", user, re.M)
    sid = first.group(1) if first else "S1"
    return {"verdict": "The change holds together. Settle whether its callers handle the new results.",
            "verdict_causes": causes[:1],
            "concerns": [{"text": "Callers handle the new results", "how": "Each caller now checks what it gets back.",
                          "stories": [sid], "assessment": "right"}],
            "ownership": [{"tag": "right", "text": "The driver owns the new checks.", "cites": [sid]}],
            "walks": [{"id": w, "title": f"Case {i} of the change", "lead": "It follows the call to where the change "
                       "lands."} for i, w in enumerate(re.findall(r"^(W\d+) \| ", user, re.M), 1)],
            "conditions": [{"id": g, "false_case": "Writes that fit"} for g in re.findall(r"^(G\d+) \| ", user, re.M)]}
