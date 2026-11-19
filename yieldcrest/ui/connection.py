"""Shared, session-safe LLM credentials for chat and decision explanations."""
import os
import streamlit as st

from yieldcrest.llm import DEFAULT_OPENAI_MODEL

NAMES = ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL")


def connection():
    try:
        values = {name: st.secrets.get(name, "") for name in NAMES}
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        values = {name: "" for name in NAMES}
    values = {name: value or os.environ.get(name, "") for name, value in values.items()}
    return {
        "gemini_key": values["GEMINI_API_KEY"] or st.session_state.get("yc_saved_key", ""),
        "openai_key": values["OPENAI_API_KEY"] or st.session_state.get("yc_saved_openai_key", ""),
        "gemini_model": st.session_state.get("yc_saved_model", "") or values["GEMINI_MODEL"],
        "openai_model": st.session_state.get("yc_saved_openai_model", "") or values["OPENAI_MODEL"] or DEFAULT_OPENAI_MODEL,
    }


def save_settings():
    # Separate storage survives Streamlit's cleanup when the floating panel is hidden.
    fields = {"yc_key_input": "yc_saved_key", "yc_model_input": "yc_saved_model",
              "yc_openai_key_input": "yc_saved_openai_key", "yc_openai_model_input": "yc_saved_openai_model"}
    for widget, saved in fields.items():
        if widget in st.session_state:
            st.session_state[saved] = st.session_state[widget]


def render_settings(config):
    with st.expander("Assistant connection"):
        st.caption("Gemini is primary. OpenAI is used automatically if Gemini fails. Shared keys belong in Streamlit secrets; personal keys below last only in this browser session.")
        st.text_input("Gemini personal key (optional)", type="password",
                      value=st.session_state.get("yc_saved_key", ""), key="yc_key_input", on_change=save_settings)
        st.text_input("Gemini model ID (optional)", value=config["gemini_model"],
                      key="yc_model_input", on_change=save_settings)
        st.text_input("OpenAI personal key (optional)", type="password",
                      value=st.session_state.get("yc_saved_openai_key", ""), key="yc_openai_key_input", on_change=save_settings)
        st.text_input("OpenAI model ID", value=config["openai_model"],
                      key="yc_openai_model_input", on_change=save_settings)
        st.caption("Configured server keys stay hidden. The request's scenario and recent conversation go to the provider used to answer it.")


def connection_label(config):
    if config["gemini_key"] and config["openai_key"]:
        return "Gemini primary · OpenAI backup configured"
    if config["openai_key"]:
        return "OpenAI configured"
    if config["gemini_key"]:
        return "Gemini configured · OpenAI backup awaits a key"
    return "Add a provider key in Assistant connection"
