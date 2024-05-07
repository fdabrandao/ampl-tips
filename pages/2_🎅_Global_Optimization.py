import sys
import os
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from apps import global_optimization, common_header, badge

st.sidebar.markdown(badge("Python_Integration"))
common_header()
global_optimization.main()
