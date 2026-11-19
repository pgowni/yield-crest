"""Provider routing with Gemini primary and OpenAI fallback."""
import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from yieldcrest.assistant_chat import TOOLS, execute_tool, build_instructions, respond as gemini_respond

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


def openai_call(key, payload):
    request = Request("https://api.openai.com/v1/responses",
                      data=json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer "+key, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        messages = {
            400: "OpenAI rejected the model or request configuration.",
            401: "OpenAI rejected the API key.",
            403: "This OpenAI project does not have the required access.",
            404: "The selected OpenAI model is unavailable.",
            429: "OpenAI quota or rate limit was reached.",
        }
        raise RuntimeError(messages.get(error.code, f"OpenAI returned status {error.code}.")) from None
    except (URLError, TimeoutError):
        raise RuntimeError("OpenAI could not be reached before the timeout.") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("OpenAI returned an unreadable response.") from None


def openai_schema(value):
    if isinstance(value, dict):
        return {key: item.lower() if key=="type" and isinstance(item, str) else openai_schema(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [openai_schema(item) for item in value]
    return value


def openai_respond(key, question, history, context, model=DEFAULT_OPENAI_MODEL):
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise ValueError("Use an OpenAI model ID only.")
    inputs = [{"role": m["role"], "content": m["content"]}
              for m in history[-8:] if not m.get("error")]
    inputs.append({"role": "user", "content": question})
    tools = [{"type": "function", "name": tool["name"], "description": tool["description"],
              "parameters": openai_schema(tool["parameters"]), "strict": False} for tool in TOOLS]
    traces = []
    for _ in range(4):
        result = openai_call(key, {
            "model": model, "instructions": build_instructions(context),
            "input": inputs, "tools": tools, "store": False,
            "include": ["reasoning.encrypted_content"], "max_output_tokens": 1800,
        })
        if result.get("status") in ("failed", "incomplete", "cancelled"):
            raise RuntimeError("OpenAI did not complete the explanation. Try a shorter question.")
        output = result.get("output", [])
        calls = [item for item in output if item.get("type")=="function_call"]
        if not calls:
            answer = "\n".join(part["text"] for item in output if item.get("type")=="message"
                               for part in item.get("content", [])
                               if part.get("type")=="output_text" and part.get("text"))
            if not answer.strip():
                raise RuntimeError("OpenAI returned no explanation.")
            return answer, traces, model
        # Preserve the response's reasoning, call IDs and other replayable items.
        inputs.extend(output)
        for call in calls:
            try:
                args = json.loads(call.get("arguments", "{}"))
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object.")
                value = execute_tool(call["name"], args, context)
            except (ValueError, TypeError, StopIteration) as error:
                value = {"error": str(error) or "Unknown request, location or service job."}
                args = {}
            traces.append({"tool": call["name"], "arguments": args, "result": value})
            inputs.append({"type": "function_call_output", "call_id": call["call_id"],
                           "output": json.dumps(value, default=str)})
    raise RuntimeError("The assistant requested too many recalculations. Try one change at a time.")


def respond_with_fallback(question, history, context, *, gemini_key="", openai_key="",
                          gemini_model="", openai_model=DEFAULT_OPENAI_MODEL):
    primary_error = ""
    if gemini_key:
        try:
            text, traces, model = gemini_respond(gemini_key, question, history, context, gemini_model)
            return {"text": text, "traces": traces, "provider": "Gemini", "model": model,
                    "fallback_reason": ""}
        except (RuntimeError, ValueError) as error:
            primary_error = str(error)
        except (KeyError, TypeError, AttributeError):
            primary_error = "Gemini returned an unexpected response."
    if openai_key:
        try:
            text, traces, model = openai_respond(openai_key, question, history, context, openai_model)
            return {"text": text, "traces": traces, "provider": "OpenAI", "model": model,
                    "fallback_reason": primary_error}
        except (RuntimeError, ValueError) as error:
            prefix = "Gemini was unavailable. " if primary_error else ""
            raise RuntimeError(prefix+str(error)) from None
    if primary_error:
        raise RuntimeError(primary_error+" Add OPENAI_API_KEY in Streamlit secrets to enable automatic backup.") from None
    raise RuntimeError("Add GEMINI_API_KEY or OPENAI_API_KEY in Streamlit secrets to enable AI explanations.")
