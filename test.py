import requests

def test_open_library_api(title, author=""):
    print(f"📡 Querying Open Library for: '{title}' by '{author}'...")
    
    url = "https://openlibrary.org/search.json"
    # Pass parameters safely using a dictionary
    payload = {
        "title": title,
        "author": author,
        "limit": 1
    }
    
    response = requests.get(url, params=payload, timeout=5)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        docs = data.get("docs", [])
        if docs:
            book_data = docs[0]
            print("\n✅ Match Found!")
            print(f"Title: {book_data.get('title')}")
            print(f"Authors: {book_data.get('author_name', ['Unknown'])}")
            # Open Library uses 'subjects' instead of a long synopsis text block
            print(f"Thematic Subjects: {book_data.get('subject', [])[:5]}") 
        else:
            print("\n⚠️ No exact match found in the database.")

test_open_library_api("The Plague", "Albert Camus")