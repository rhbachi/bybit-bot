import sys
import os

print(f"Running: {sys.argv}", flush=True)
if "streamlit" not in sys.argv[0]:
    print("Auto-relaunching Dashboard via Streamlit...", flush=True)
    os.execv(sys.executable, ["python", "-m", "streamlit", "run", sys.argv[0], "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"])

import streamlit as st
if "streamlit" in sys.modules:
    print("Streamlit successfully loaded and running!")
st.write("Hello Streamlit!")
