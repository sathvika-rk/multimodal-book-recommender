import streamlit as st
from google import genai
from PIL import Image
import json
import requests
import time

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shelf Picker RAG AI",
    page_icon="📚",
    layout="centered",
)

# ── Helper: Open Library API retrieval ───────────────────────────────────────
def fetch_book_metadata(title, author=""):
    """
    Queries Open Library using a broad global search string for maximum fuzziness.
    EXPLICITLY requests the 'subject' field to prevent empty data returns.
    """
    try:
        search_query = f"{title} {author}".strip()
        
        # THE FIX: Tell Open Library exactly which fields to return
        params = {
            "q": search_query, 
            "fields": "title,author_name,subject",
            "limit": 1
        }

        response = requests.get(
            "https://openlibrary.org/search.json",
            params=params,
            timeout=8,
        )

        if response.status_code == 200:
            docs = response.json().get("docs", [])
            if docs:
                book_data = docs[0]
                
                # Extract the tags (Open Library returns them as a list of strings here)
                subjects = book_data.get("subject") or []

                if subjects:
                    # We have tags! Take the top 5
                    genres = subjects[:5]
                    synopsis = f"Verified catalog entry found under themes: {', '.join(genres)}."
                else:
                    # Smart Fallback: The book is in the database, but nobody tagged it.
                    genres = ["Needs Classification"]
                    synopsis = "Book found, but catalog tags are empty. Use internal knowledge."
                    
                return {"genres": genres, "synopsis": synopsis}

    except requests.exceptions.Timeout:
        print("⚡ Open Library API timed out.")
    except Exception as e:
        print(f"⚡ Search Error: {e}")

    # True fallback if the book is completely missing from Open Library
    return {
        "genres": ["Unknown"],
        "synopsis": "No catalog data found. Use your own knowledge of this title.",
    }

# ── Helper: robust JSON extraction from LLM output ───────────────────────────
def extract_json(text):
    """Strips markdown fences and extracts the first JSON array."""
    text = text.strip().replace("```json", "").replace("```", "").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No JSON array found in model response.")
    return json.loads(text[start : end + 1])

# ── Title & description ───────────────────────────────────────────────────────
st.title("📚 Shelf Picker AI — RAG Pipeline")
st.write(
    "Upload a shelf photo and describe your mood. The pipeline extracts every "
    "visible book, retrieves subject data from Open Library, then reasons over "
    "real catalog data to recommend exactly what to grab."
)

# ── Sidebar: API key ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 Configuration")
    api_key = None
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.success("Cloud API key loaded securely.")
    except Exception:
        pass

    if not api_key:
        api_key = st.text_input("Gemini API Key", type="password")
        st.markdown("---")
        st.caption("Your key is used only for this session and is never saved.")

# ── Main inputs ───────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "📸 Step 1 — Upload a photo of a bookshelf",
    type=["jpg", "jpeg", "png"],
)
user_preference = st.text_input(
    "✍️ Step 2 — What are you in the mood for?",
    placeholder="e.g., cyber-punk sci-fi, dark psychology",
)

# ── Input validation guard ────────────────────────────────────────────────────
missing = []
if not api_key: missing.append("a Gemini API key")
if not uploaded_file: missing.append("a shelf photo")
if not user_preference: missing.append("your reading preference")
if missing:
    st.info(f"Still needed: {', '.join(missing)}.")

# ── RAG pipeline ──────────────────────────────────────────────────────────────
MAX_BOOKS_TO_RETRIEVE = 15

if uploaded_file and user_preference and api_key:
    image = Image.open(uploaded_file)
    st.image(image, caption="Your bookshelf", use_container_width=True)

    if st.button("⚙️ Execute RAG Pipeline", type="primary"):
        client = genai.Client(api_key=api_key)

        # ── STAGE 1: Vision extraction (WITH AUTOMATIC RETRIES) ───────────────
        books_list = []
        with st.status("🚀 Stage 1: Extracting titles via Vision LLM…") as status:
            extraction_prompt = """
Analyze the bookshelf image. Extract the title and author for every legible book.
Output ONLY a valid raw JSON array with objects using keys "title" and "author".
Do not include markdown fences or any text outside the JSON array.
Example: [{"title": "The Hobbit", "author": "J.R.R. Tolkien"}]
If an author is not visible, use an empty string for that field.
"""
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    extraction_response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[extraction_prompt, image],
                    )
                    books_list = extract_json(extraction_response.text)
                    break  # Success! Break out of retry loop
                    
                except Exception as e:
                    # Catch temporary server traffic overloads (503)
                    if "503" in str(e) and attempt < max_retries - 1:
                        status.update(label=f"⏳ Google API busy. Retrying in 3s (Attempt {attempt + 2}/{max_retries})…")
                        time.sleep(3)
                    else:
                        status.update(label="❌ Stage 1 Failed: Could not process request.", state="error")
                        st.error(f"API Error: {e}")
                        st.stop()

            if not books_list:
                status.update(label="⚠️ Stage 1: No readable books found.", state="error")
                st.warning("The model couldn't read any book titles. Try a clearer photo.")
                st.stop()

            if len(books_list) > MAX_BOOKS_TO_RETRIEVE:
                books_list = books_list[:MAX_BOOKS_TO_RETRIEVE]

            status.update(
                label=f"✅ Stage 1 Complete: {len(books_list)} books detected.",
                state="complete",
            )

        if books_list:
            with st.expander("📋 View extracted book list"):
                st.json(books_list)

        # ── STAGE 2: Open Library retrieval ──────────────────────────────────
        retrieved_knowledge_base = []
        with st.status("🔍 Stage 2: Querying Open Library…") as status:
            st.caption(f"Fetching up to {len(books_list)} books — this may take 15–30 seconds.")
            for book in books_list:
                title = book.get("title", "").strip()
                author = book.get("author", "").strip()
                if not title:
                    continue
                status.update(label=f"🔍 Fetching: {title}…")
                metadata = fetch_book_metadata(title, author)
                retrieved_knowledge_base.append({
                    "title": title,
                    "author": author,
                    "genres": metadata["genres"],
                    "synopsis": metadata["synopsis"],
                })
            status.update(
                label=f"✅ Stage 2 Complete: {len(retrieved_knowledge_base)} entries retrieved.",
                state="complete",
            )

        if retrieved_knowledge_base:
            with st.expander("📚 View retrieved knowledge base"):
                st.json(retrieved_knowledge_base)

        # ── STAGE 3: Augmented generation ─────────────────────────────────────
        with st.status("🧠 Stage 3: Synthesizing recommendations…") as status:
            generation_prompt = f"""
You are an expert literary analyst helping a user choose a book from a physical shelf.

User's preference: "{user_preference}"

Below is a knowledge base of books visible on that shelf, enriched with
catalog subject tags retrieved from Open Library.

Knowledge base:
{json.dumps(retrieved_knowledge_base, indent=2)}

Task:
Select the top 2–3 books from this knowledge base that best match the user's preference.

Guidance:
- If a book has rich subject tags, use them as your primary evidence.
- If a book's genres say "Needs Classification" or "Unknown", rely on your own 
  deep background knowledge of that title and author to evaluate the match.
- Prioritize books whose subjects, themes, or known plot directly overlap with "{user_preference}".

For each recommendation provide:
1. **Title** and **Author**
2. A concise explanation of why it matches the user's preference. Reference the 
   Open Library subject tags if available, or your own knowledge if they were missing.

STRICT RULE: Only recommend books present in the knowledge base above.
Format your response as clean Markdown.
"""
            try:
                generation_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[generation_prompt],
                )
                status.update(label="✅ Stage 3 Complete: Recommendations ready!", state="complete")
                st.markdown("---")
                st.markdown("### 🎯 Data-Backed Recommendations")
                st.markdown(generation_response.text)

            except Exception as e:
                status.update(label="❌ Stage 3 Failed.", state="error")
                st.error(str(e))