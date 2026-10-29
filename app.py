# CampusFix, a campus maintenance reporting app for the LION Code Challenge 2026
# Run with: streamlit run app.py
import sqlite3
import os
import uuid
from datetime import datetime
from difflib import SequenceMatcher
import pandas as pd
import streamlit as st

DB = "campusfix.db"
PHOTO_DIR = "photos"
CATEGORIES = ["Electrical", "Plumbing", "Cleaning", "Furniture", "Safety", "IT", "Other"]
LOCATIONS = ["Lares Building", "Sutherland Building", "Woodland Building", "Rydal Building", "Library", "Athletic Center", "Parking Lot", "Outdoor Grounds"]
STATUSES = ["Reported", "In Progress", "Resolved"]
# Words that point to a category, used to suggest one from the description
KEYWORDS = {
    "Electrical": ["light", "outlet", "power", "bulb", "socket", "flicker", "switch"],
    "Plumbing": ["leak", "tap", "faucet", "toilet", "sink", "water", "drain", "pipe"],
    "Cleaning": ["trash", "dirty", "spill", "mess", "smell", "garbage"],
    "Furniture": ["chair", "desk", "table", "door", "jammed", "broken seat", "locker"],
    "Safety": ["ice", "slippery", "exposed", "hazard", "fire", "alarm", "unsafe"],
    "IT": ["wifi", "projector", "printer", "computer", "screen", "network", "login"],
}

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, category TEXT, location TEXT, photo TEXT, status TEXT, upvotes INTEGER DEFAULT 0, created TEXT, updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, status TEXT, note TEXT, changed TEXT)")
    # Load made up sample data the first time so the app is not empty
    if conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0:
        samples = [
            ("Flickering hallway light", "The ceiling light outside room 120 keeps flickering", "Electrical", "Lares Building", "In Progress"),
            ("Leaking sink tap", "Second floor bathroom sink tap will not stop dripping", "Plumbing", "Sutherland Building", "Reported"),
            ("Jammed classroom door", "Door to room 204 sticks and is hard to open", "Furniture", "Woodland Building", "Reported"),
            ("Dead outlet by study tables", "Outlet near the back study tables has no power", "Electrical", "Library", "Resolved"),
            ("Projector not turning on", "Projector in room 110 will not power on", "IT", "Rydal Building", "Reported"),
        ]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for t, d, c, l, s in samples:
            cur = conn.execute("INSERT INTO reports (title, description, category, location, photo, status, upvotes, created, updated) VALUES (?,?,?,?,?,?,?,?,?)", (t, d, c, l, "", s, 0, now, now))
            conn.execute("INSERT INTO history (report_id, status, note, changed) VALUES (?,?,?,?)", (cur.lastrowid, s, "Sample data", now))
    conn.commit()
    return conn

def suggest_category(text):
    # Count keyword hits for each category and return the best match
    text = text.lower()
    scores = {c: sum(w in text for w in words) for c, words in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Other"

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_duplicates(conn, title, description, category, location):
    # Score open reports on text similarity plus a bonus for same location and category
    rows = conn.execute("SELECT * FROM reports WHERE status != 'Resolved'").fetchall()
    matches = []
    for r in rows:
        score = 0.6 * similarity(title + " " + description, r["title"] + " " + r["description"])
        if r["location"] == location:
            score += 0.25
        if r["category"] == category:
            score += 0.15
        if score >= 0.5:
            matches.append((score, r))
    matches.sort(key=lambda m: m[0], reverse=True)
    return matches[:3]

def save_report(conn, title, description, category, location, photo_file):
    photo_path = ""
    if photo_file is not None:
        os.makedirs(PHOTO_DIR, exist_ok=True)
        photo_path = os.path.join(PHOTO_DIR, str(uuid.uuid4()) + "_" + photo_file.name)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getbuffer())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute("INSERT INTO reports (title, description, category, location, photo, status, upvotes, created, updated) VALUES (?,?,?,?,?,?,?,?,?)", (title, description, category, location, photo_path, "Reported", 0, now, now))
    conn.execute("INSERT INTO history (report_id, status, note, changed) VALUES (?,?,?,?)", (cur.lastrowid, "Reported", "Report submitted", now))
    conn.commit()
    return cur.lastrowid

def upvote(conn, report_id):
    conn.execute("UPDATE reports SET upvotes = upvotes + 1 WHERE id = ?", (report_id,))
    conn.commit()

def update_status(conn, report_id, status, note):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute("UPDATE reports SET status = ?, updated = ? WHERE id = ?", (status, now, report_id))
    conn.execute("INSERT INTO history (report_id, status, note, changed) VALUES (?,?,?,?)", (report_id, status, note, now))
    conn.commit()

def show_report(conn, r):
    st.markdown(f"**#{r['id']} {r['title']}**  |  {r['category']}  |  {r['location']}")
    st.write(r["description"])
    st.progress((STATUSES.index(r["status"]) + 1) / 3, text=f"Status: {r['status']}  |  Upvotes: {r['upvotes']}")
    if r["photo"] and os.path.exists(r["photo"]):
        st.image(r["photo"], width=250, caption="Photo attached to report")
    hist = conn.execute("SELECT status, note, changed FROM history WHERE report_id = ? ORDER BY id", (r["id"],)).fetchall()
    with st.expander("Status history"):
        for h in hist:
            st.write(f"{h['changed']}  {h['status']}  {h['note']}")

st.set_page_config(page_title="CampusFix", layout="wide")
conn = init_db()
st.title("CampusFix")
st.caption("Report campus maintenance issues, avoid duplicates, and follow each issue until it is fixed.")
page = st.sidebar.radio("Go to", ["Report an issue", "Browse and search", "Facilities staff", "Dashboard"])

if page == "Report an issue":
    title = st.text_input("Title")
    description = st.text_area("Description")
    suggested = suggest_category(title + " " + description) if (title or description) else "Other"
    if title or description:
        st.info(f"Suggested category: {suggested}")
    category = st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(suggested))
    location = st.selectbox("Campus location", LOCATIONS)
    photo = st.file_uploader("Attach a photo (optional)", type=["png", "jpg", "jpeg"])
    if st.button("Check and submit"):
        if not title or not description:
            st.error("Please add a title and a description.")
        else:
            st.session_state["pending"] = (title, description, category, location)
            st.session_state["dupes"] = [m[1]["id"] for m in find_duplicates(conn, title, description, category, location)]
    if "pending" in st.session_state:
        dupes = st.session_state["dupes"]
        if dupes:
            st.warning("These existing reports look similar. Upvote one if it is the same problem.")
            for rid in dupes:
                r = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
                show_report(conn, r)
                if st.button(f"Upvote #{rid}, it is the same issue", key=f"up{rid}"):
                    upvote(conn, rid)
                    st.success(f"Thanks, your upvote was added to report #{rid}.")
                    del st.session_state["pending"]
            if "pending" in st.session_state and st.button("None of these, submit my report"):
                new_id = save_report(conn, *st.session_state["pending"], photo)
                st.success(f"Report #{new_id} submitted.")
                del st.session_state["pending"]
        else:
            new_id = save_report(conn, *st.session_state["pending"], photo)
            st.success(f"No similar reports found. Report #{new_id} submitted.")
            del st.session_state["pending"]

elif page == "Browse and search":
    c1, c2, c3 = st.columns(3)
    cat = c1.selectbox("Category", ["All"] + CATEGORIES)
    loc = c2.selectbox("Location", ["All"] + LOCATIONS)
    stat = c3.selectbox("Status", ["All"] + STATUSES)
    search = st.text_input("Search by keyword")
    query = "SELECT * FROM reports WHERE 1=1"
    params = []
    if cat != "All":
        query += " AND category = ?"
        params.append(cat)
    if loc != "All":
        query += " AND location = ?"
        params.append(loc)
    if stat != "All":
        query += " AND status = ?"
        params.append(stat)
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    rows = conn.execute(query + " ORDER BY upvotes DESC, id DESC", params).fetchall()
    st.write(f"{len(rows)} reports found")
    for r in rows:
        show_report(conn, r)
        st.divider()

elif page == "Facilities staff":
    # Staff see open reports ranked by upvotes so the most reported issues come first
    rows = conn.execute("SELECT * FROM reports WHERE status != 'Resolved' ORDER BY upvotes DESC, id").fetchall()
    if not rows:
        st.success("No open reports.")
    for r in rows:
        show_report(conn, r)
        new_status = st.selectbox("Update status", STATUSES, index=STATUSES.index(r["status"]), key=f"s{r['id']}")
        note = st.text_input("Note for reporters", key=f"n{r['id']}")
        if st.button("Save update", key=f"b{r['id']}"):
            update_status(conn, r["id"], new_status, note or "Status updated by facilities")
            st.rerun()
        st.divider()

elif page == "Dashboard":
    df = pd.read_sql_query("SELECT * FROM reports", conn)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total reports", len(df))
    c2.metric("Open", int((df["status"] != "Resolved").sum()))
    c3.metric("Resolved", int((df["status"] == "Resolved").sum()))
    st.subheader("Reports by building")
    st.bar_chart(df.groupby("location").size())
    st.subheader("Reports by category")
    st.bar_chart(df.groupby("category").size())
