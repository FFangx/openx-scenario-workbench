"""Model settings using the established native workspace controls."""
import hashlib
from dataclasses import replace

import streamlit as st

from .llm_service import ModelClient, ModelConfig, ModelError, base_url, load_config, save_config


def model_settings(language):
    zh = language == "zh"
    st.subheader("大模型" if zh else "Language model")
    st.caption("用于 PDF 场景识别、分类和匹配解释。兼容 Chat Completions 接口。" if zh else
               "Used for PDF extraction, classification and explanations. Chat Completions compatible.")
    try:
        saved = load_config()
    except (ValueError, OSError):
        saved = ModelConfig()
        st.warning("保存的模型设置无法读取，请重新配置。" if zh else "Saved model settings could not be read.")
    if st.session_state.pop("clear_model_key_input", False):
        st.session_state.pop("model_api_key", None)
    endpoint = st.text_input("服务地址 / Base URL", value=saved.base_url, key="model_base_url",
                             help="例如 https://api.deepseek.com 或供应商的 /v1 地址")
    key = st.text_input("API Key", type="password", key="model_api_key",
                        placeholder=("已保存；留空保持" if saved.api_key else "请输入 Key") if zh else
                        ("Saved; leave blank to keep" if saved.api_key else "Enter API key"))
    # An existing credential must never silently follow an edited endpoint.
    try:
        effective_key = key.strip() or (saved.api_key if base_url(endpoint) == base_url(saved.base_url) else "")
    except ModelError:
        effective_key = key.strip()
    fingerprint = hashlib.sha256((endpoint + "\0" + effective_key).encode()).hexdigest()
    if st.button("获取模型清单" if zh else "Fetch model list", key="fetch_models", icon=":material/refresh:"):
        try:
            with st.spinner("读取模型清单…" if zh else "Loading models…"):
                models = ModelClient(replace(saved, base_url=endpoint, api_key=effective_key)).models()
            st.session_state.model_catalog = (fingerprint, models)
        except ModelError as error:
            st.session_state.pop("model_catalog", None)
            st.error(str(error))
    catalog = st.session_state.get("model_catalog")
    if catalog and catalog[0] == fingerprint:
        options = ["", *catalog[1]]
        def choose_model():
            if st.session_state.model_choice:
                st.session_state.model_name = st.session_state.model_choice
        st.selectbox("可用模型" if zh else "Available models", options, key="model_choice",
                     format_func=lambda value: value or ("选择模型或在下方手动输入" if zh else "Select or enter below"),
                     on_change=choose_model)
    model = st.text_input("模型名（可手动输入）" if zh else "Model ID (editable)", value=saved.model, key="model_name")
    with st.expander("高级参数" if zh else "Advanced options"):
        thinking = st.checkbox("DeepSeek 思考模式" if zh else "DeepSeek thinking mode", value=saved.thinking, key="model_thinking")
        maximum = st.number_input("最大输出 tokens" if zh else "Maximum output tokens", min_value=256, max_value=131072,
                                  value=saved.max_tokens, step=256, key="model_max_tokens")
        timeout = st.number_input("超时（秒）" if zh else "Timeout (seconds)", min_value=10, max_value=1800,
                                  value=saved.timeout, step=10, key="model_timeout")
    draft = ModelConfig(endpoint, model.strip(), effective_key, thinking, int(maximum), int(timeout))
    test, save = st.columns(2)
    with test:
        if st.button("测试所选模型" if zh else "Test selected model", key="test_model", icon=":material/network_check:", use_container_width=True):
            try:
                with st.spinner("发送简短 JSON 测试…" if zh else "Testing a short JSON response…"):
                    ModelClient(draft).probe()
                st.success(("模型可用：" if zh else "Model available: ") + draft.model)
            except ModelError as error:
                st.error(str(error))
    with save:
        if st.button("保存模型配置" if zh else "Save model settings", key="save_model", icon=":material/save:", use_container_width=True):
            try:
                save_config(draft)
                st.session_state.clear_model_key_input = True
                st.success("模型配置已保存。" if zh else "Model settings saved.")
            except ModelError as error:
                st.error(str(error))
    st.caption("测试会发送一条简短请求；解析 PDF 时会发送文档文字。Key 只保存在本机，Windows 使用当前用户加密。" if zh else
               "Testing sends a short request; PDF extraction sends document text. The key stays local and is user-encrypted on Windows.")
    if saved.api_key and st.button("移除保存的 Key" if zh else "Remove saved key", key="clear_model_key"):
        save_config(replace(saved, api_key=""))
        st.session_state.clear_model_key_input = True
        st.rerun()
