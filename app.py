import streamlit as st
import requests
from bs4 import BeautifulSoup
import spacy
import subprocess
from spacy.util import is_package
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from urllib.parse import urlparse
from textstat import flesch_reading_ease, flesch_kincaid_grade
import pandas as pd
from docx import Document

# --- Load or Download spaCy model ---
model_name = "en_core_web_sm"
if not is_package(model_name):
    subprocess.run(["python", "-m", "spacy", "download", model_name])
nlp = spacy.load(model_name)

# --- KeyBERT model ---
kw_model = KeyBERT(model=SentenceTransformer('all-MiniLM-L6-v2'))

# --- Streamlit UI Setup ---
st.set_page_config(page_title="SEO Content Intelligence", layout="wide")
st.title("🔍 SEO Content Intelligence Tool")

# --- Utility Functions ---
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

@st.cache_data(show_spinner=False)
def extract_text_from_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = [p.get_text() for p in soup.find_all('p') if len(p.get_text()) > 40]
        return "\n".join(paragraphs)
    except Exception as e:
        return f"ERROR: {str(e)}"

def extract_text_from_file(uploaded_file):
    if uploaded_file.name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8")
    elif uploaded_file.name.endswith(".docx"):
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""

def analyze_text(input_text):
    doc = nlp(input_text)
    keywords = kw_model.extract_keywords(input_text, top_n=10)
    entities = list(set(ent.text for ent in doc.ents if len(ent.text.strip()) > 1))
    noun_chunks = list(set(chunk.text.lower() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 3))
    sentences = input_text.split(".")
    meta_title = sentences[0][:60] + "..." if sentences else "N/A"
    meta_description = input_text.strip()[:160] + "..."
    try:
        reading_score = flesch_reading_ease(input_text)
        reading_grade = flesch_kincaid_grade(input_text)
    except:
        reading_score = reading_grade = "N/A"
    word_list = input_text.lower().split()
    density_info = [(kw, round(word_list.count(kw.lower()) / len(word_list) * 100, 2)) for kw, _ in keywords]
    return keywords, density_info, entities, noun_chunks, meta_title, meta_description, reading_score, reading_grade

# --- Streamlit Tabs ---
tab1, tab2 = st.tabs(["📝 Single Content Analysis", "⚔️ Competitor Comparison"])

# --- Tab 1: Single Content ---
with tab1:
    st.subheader("Choose input method:")
    input_mode = st.radio("", ["Paste Text", "Enter URL", "Upload File"], horizontal=True)
    input_text = ""

    if input_mode == "Paste Text":
        input_text = st.text_area("Paste your content:", height=300)

    elif input_mode == "Enter URL":
        url = st.text_input("Enter article/blog URL:")
        if url and is_valid_url(url):
            with st.spinner("Fetching content..."):
                fetched = extract_text_from_url(url)
            if fetched.startswith("ERROR"):
                st.error("❌ Failed to fetch from the URL.")
            elif len(fetched) < 100:
                st.warning("⚠️ Not enough text found at URL.")
            else:
                input_text = fetched
                st.success("✅ Content fetched.")
                st.text_area("Fetched Content", input_text, height=300)

    elif input_mode == "Upload File":
        uploaded_file = st.file_uploader("Upload .txt or .docx file", type=["txt", "docx"])
        if uploaded_file:
            input_text = extract_text_from_file(uploaded_file)
            st.text_area("File Content", input_text, height=300)

    if st.button("📈 Analyze Content") and input_text.strip():
        with st.spinner("Analyzing..."):
            (keywords, density, entities, chunks, title, desc, score, grade) = analyze_text(input_text)

        st.subheader("🔑 Top Keywords")
        for kw, s in keywords:
            st.markdown(f"- **{kw}** (score: {round(s, 2)})")

        st.subheader("📊 Keyword Density (%)")
        for kw, d in density:
            st.markdown(f"- {kw}: {d}%")

        st.subheader("🏷️ Named Entities")
        st.markdown(", ".join(entities) if entities else "None found.")

        st.subheader("🧩 Topics (Noun Phrases)")
        st.markdown(", ".join(chunks[:10]) if chunks else "None found.")

        st.subheader("📝 Meta Title")
        st.success(title)

        st.subheader("📝 Meta Description")
        st.info(desc)

        st.subheader("📖 Readability")
        st.markdown(f"- Flesch Reading Ease: **{score}**")
        st.markdown(f"- Grade Level: **{grade}**")

        df = pd.DataFrame({
            "Keyword": [kw for kw, _ in keywords],
            "Score": [round(s, 2) for _, s in keywords],
            "Density (%)": [d for _, d in density]
        })
        st.download_button("⬇️ Download CSV", data=df.to_csv(index=False), file_name="seo_report.csv", mime="text/csv")

# --- Tab 2: Competitor Comparison ---
with tab2:
    st.subheader("Enter URLs of two competitor blog/articles:")

    col1, col2 = st.columns(2)
    with col1:
        url1 = st.text_input("Competitor A URL")
    with col2:
        url2 = st.text_input("Competitor B URL")

    if st.button("⚔️ Compare Competitors"):
        if not (url1 and url2):
            st.warning("Please enter both URLs.")
        elif not (is_valid_url(url1) and is_valid_url(url2)):
            st.error("Please enter valid URLs.")
        else:
            with st.spinner("Fetching & analyzing both URLs..."):
                text1 = extract_text_from_url(url1)
                text2 = extract_text_from_url(url2)

                data1 = analyze_text(text1)
                data2 = analyze_text(text2)

            st.subheader("🔍 Competitor Comparison Summary")

            comp = pd.DataFrame({
                "Metric": ["Keyword Count", "Unique Entities", "Readability", "Grade Level"],
                "Competitor A": [len(data1[0]), len(data1[2]), data1[6], data1[7]],
                "Competitor B": [len(data2[0]), len(data2[2]), data2[6], data2[7]]
            })
            st.table(comp)

            st.subheader("📌 Competitor A Top Keywords")
            st.markdown(", ".join([kw for kw, _ in data1[0]]))

            st.subheader("📌 Competitor B Top Keywords")
            st.markdown(", ".join([kw for kw, _ in data2[0]]))

# --- Footer ---
st.markdown(
    """
    <hr style="margin-top: 50px;">
    <div style='text-align: center; color: gray;'>
        Made with ❤️ by <strong>Hardik Batwal</strong>
    </div>
    """,
    unsafe_allow_html=True
)
