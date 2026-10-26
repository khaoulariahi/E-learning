"""Settings tab: read-only view of the configuration."""

import pandas as pd
import streamlit as st
import yaml

from assistant.core.config import ConfigError, get_settings
from assistant.core.runtime.limiter import budget_rpm


def render() -> None:
    s = get_settings()
    try:
        key = s.api_key
        st.success(f"NVIDIA API key loaded (…{key[-4:]})")
    except ConfigError as e:
        st.error(str(e))

    st.subheader("Models")
    st.dataframe(
        pd.DataFrame([
            {"role": role, "model": m.id, "fallbacks": ", ".join(m.fallbacks), "rpm": m.rpm,
             "UI rpm budget": round(budget_rpm(role), 1), "max in flight": m.max_in_flight}
            for role, m in s.models.items()
        ]),
        hide_index=True, width="stretch",
    )
    st.subheader("config.yaml")
    st.code(yaml.safe_dump(s.raw, allow_unicode=True, sort_keys=False), language="yaml")
    st.caption(f"Data directory: {s.data_dir}")
