import streamlit as st
from supabase import create_client, Client

# Load from Streamlit secrets (works both locally and on Streamlit Cloud)
URL = st.secrets["supabase"]["url"]
KEY = st.secrets["supabase"]["key"]

supabase: Client = create_client(URL, KEY)

st.title("Supabase ↔ Streamlit test")

if st.button("Fetch rows from `patients` table"):
    res = supabase.table("patients").select("*").execute()
    if res.error:
        st.error(f"Error: {res.error.message}")
    else:
        st.write(res.data)
