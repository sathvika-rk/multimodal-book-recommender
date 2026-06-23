import streamlit as st
from google import genai
from PIL import Image

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shelf Picker AI",
    page_icon="📚",
    layout="centered",
)

# ── Title & description ───────────────────────────────────────────────────────
st.title("📚 Shelf Picker AI")
st.write(
    "Snap a photo of any bookshelf, tell me what you're in the mood for, "
    "and I'll point you to the best matches **on that exact shelf**."
)

# ── Sidebar: API key (CRASH-PROOF VERSION) ───────────────────────────────────
with st.sidebar:
    st.header("🔑 Configuration")
    
    api_key = None
    
    # Safely attempt to read from cloud secrets without crashing on local runs
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.success("Cloud API key loaded securely.")
    except Exception:
        # If no secrets file exists (like on your Mac), catch the error and do nothing
        pass

    # Fallback: If no cloud key was found, show the manual input field
    if not api_key:
        api_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Paste your Google Gemini API key here. It is never stored.",
        )
        st.markdown("---")
        st.caption("Your key is used only for this session and is never saved.")

# ── Main inputs ───────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "📸 Step 1 — Upload a photo of a bookshelf",
    type=["jpg", "jpeg", "png"],
)

user_preference = st.text_input(
    "✍️ Step 2 — What are you in the mood for?",
    placeholder="e.g., fast-paced thriller, feel-good romance, philosophy",
)

# ── Guard: remind the user what's still missing ───────────────────────────────
missing = []
if not api_key:
    missing.append("a Gemini API key (sidebar)")
if not uploaded_file:
    missing.append("a shelf photo")
if not user_preference:
    missing.append("your reading preference")

if missing:
    st.info(f"Still needed: {', '.join(missing)}.")

# ── Main logic: only active when all three inputs are present ─────────────────
if uploaded_file and user_preference and api_key:

    # Show image only inside the action block so the UI stays clean
    image = Image.open(uploaded_file)
    st.image(image, caption="Your bookshelf", use_container_width=True)

    if st.button("🔍 Scan Shelf & Recommend", type="primary"):
        with st.spinner("Scanning the shelf…"):

            prompt = f"""
You are an expert personal librarian. A user is standing in front of a physical
bookshelf and has sent you a photo of it.

Their reading preference: "{user_preference}"

Your task:
1. Carefully examine the image and identify every book whose title or author is
   at least partially legible on a spine or cover.
2. From those books ONLY, select the 2–3 titles that best match the user's
   stated preference.
3. For each recommendation provide:
   - **Title** and **Author** (exactly as visible in the image)
   - **Why it fits** — one or two sentences connecting this specific book to
     the user's preference.

STRICT RULES:
- Recommend ONLY books visible in this image. Do not invent or suggest books
  from outside the photo.
- If you cannot read a title clearly enough to be confident, skip it.
- If no books on the shelf match the preference, say so honestly and explain
  what genres you do see.

Format your answer as a clean Markdown list.
"""

            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[prompt, image],
                )
                st.markdown("### 🎯 Best Picks From This Shelf")
                st.markdown(response.text)

            except Exception as e:
                error_msg = str(e)
                if "API_KEY" in error_msg.upper() or "401" in error_msg or "403" in error_msg:
                    st.error(
                        "❌ **Invalid API key.** Please double-check the key "
                        "you entered in the sidebar."
                    )
                elif "quota" in error_msg.lower() or "429" in error_msg:
                    st.error(
                        "❌ **Rate limit reached.** You've hit your Gemini API "
                        "quota. Wait a moment and try again."
                    )
                else:
                    st.error(f"❌ **Something went wrong:** {error_msg}")