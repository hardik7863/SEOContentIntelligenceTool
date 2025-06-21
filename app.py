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
import torch

# --- Load or Download spaCy model ---
model_name = "en_core_web_sm"
try:
    if not is_package(model_name):
        subprocess.run(["python", "-m", "spacy", "download", model_name], check=True)
    nlp = spacy.load(model_name)
except Exception as e:
    st.error(f"❌ Failed to load spaCy model: {e}")
    nlp = None

# --- Load KeyBERT with safe fallback ---
@st.cache_resource
def load_keybert_model():
    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
        if hasattr(model, "to_empty"):
            model.to_empty(device)
        return KeyBERT(model=model)
    except NotImplementedError:
        st.warning("⚠️ GPU issue, falling back to CPU.")
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            if hasattr(model, "to_empty"):
                model.to_empty("cpu")
            return KeyBERT(model=model)
        except Exception as e:
            st.error(f"❌ CPU fallback failed: {e}")
            return None
    except Exception as e:
        st.error(f"❌ Model loading error: {e}")
        return None

kw_model = load_keybert_model()

# --- UI Setup ---
st.set_page_config(page_title="SEO Content Intelligence", layout="wide")
st.title("🔍 SEO Content Intelligence Tool")

# --- Utils ---
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
    try:
        if uploaded_file.name.endswith(".txt"):
            return uploaded_file.read().decode("utf-8")
        elif uploaded_file.name.endswith(".docx"):
            doc = Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        st.error(f"❌ File reading error: {e}")
    return ""

def analyze_text(input_text):
    try:
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
    except Exception as e:
        st.error(f"❌ Text analysis failed: {e}")
        return [], [], [], [], "N/A", "N/A", "N/A", "N/A"

# --- Interface Tabs ---
tab1, tab2 = st.tabs(["📝 Single Content Analysis", "⚔️ Competitor Comparison"])

with tab1:
    st.subheader("Choose input method:")
    input_mode = st.radio("", ["Paste Text", "Enter URL", "Upload File"], horizontal=True)
    input_text = ""

    if input_mode == "Paste Text":
        input_text = st.text_area("Paste your content:", height=300)
        st.caption("📝 Tip: Paste a well-formatted blog or article.")

    elif input_mode == "Enter URL":
        url = st.text_input("Enter blog/article URL:")
        if url and is_valid_url(url):
            with st.spinner("Fetching content..."):
                fetched = extract_text_from_url(url)
            if fetched.startswith("ERROR"):
                st.error("❌ Failed to fetch from the URL.")
            elif len(fetched) < 100:
                st.warning("⚠️ Not enough text found.")
            else:
                input_text = fetched
                st.success("✅ Content fetched.")
                st.text_area("Fetched Content", input_text, height=300)

    elif input_mode == "Upload File":
        uploaded_file = st.file_uploader("Upload .txt or .docx file", type=["txt", "docx"])
        if uploaded_file:
            input_text = extract_text_from_file(uploaded_file)
            st.text_area("File Content", input_text, height=300)

    if st.button("📈 Analyze Content"):
        if not input_text.strip():
            st.warning("⚠️ Please enter some content.")
        elif kw_model is None or nlp is None:
            st.error("❌ NLP model or KeyBERT not loaded.")
        else:
            with st.spinner("Analyzing..."):
                (keywords, density, entities, chunks, title, desc, score, grade) = analyze_text(input_text)

            st.subheader("🔑 Top Keywords")
            for kw, s in keywords:
                st.markdown(f"- **{kw}** (score: {round(s, 2)})")

            st.subheader("📊 Keyword Density (%)")
            for kw, d in density:
                st.markdown(f"- {kw}: {d}%")

            st.subheader("🏷️ Named Entities")
            st.markdown(", ".join(entities) if entities else "None")

            st.subheader("🧩 Topics (Noun Phrases)")
            st.markdown(", ".join(chunks[:10]) if chunks else "None")

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

with tab2:
    st.subheader("Compare two competitors:")
    col1, col2 = st.columns(2)
    with col1:
        url1 = st.text_input("Competitor A URL")
    with col2:
        url2 = st.text_input("Competitor B URL")

    if st.button("⚔️ Compare Competitors"):
        if not (url1 and url2):
            st.warning("Please enter both URLs.")
        elif not (is_valid_url(url1) and is_valid_url(url2)):
            st.error("Invalid URL(s).")
        else:
            with st.spinner("Analyzing both URLs..."):
                text1 = extract_text_from_url(url1)
                text2 = extract_text_from_url(url2)
                data1 = analyze_text(text1)
                data2 = analyze_text(text2)

            st.subheader("📊 Comparison Summary")
            comp = pd.DataFrame({
                "Metric": ["Keyword Count", "Entities", "Readability", "Grade Level"],
                "Competitor A": [len(data1[0]), len(data1[2]), data1[6], data1[7]],
                "Competitor B": [len(data2[0]), len(data2[2]), data2[6], data2[7]],
            })
            st.table(comp)

            st.subheader("📌 Competitor A Keywords")
            st.markdown(", ".join([kw for kw, _ in data1[0]]))

            st.subheader("📌 Competitor B Keywords")
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
