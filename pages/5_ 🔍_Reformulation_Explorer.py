import sys
import os
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from apps import reformulation_explorer, common_header, badge

common_header()
reformulation_explorer.main()
st.sidebar.markdown(badge("Python_Integration"))
