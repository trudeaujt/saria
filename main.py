from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, AnyHttpUrl
from datetime import datetime
from typing import List
import sqlite3

app = FastAPI()

def get_db(db_name="saria.db"):
    db = sqlite3.connect(db_name)
    db.row_factory = sqlite3.Row
    return db

# Pydantic models for request and response validation
class LinkCreate(BaseModel):
    original_url: AnyHttpUrl
    short_code: str

class LinkTag(BaseModel):
    tag: str

class CustomDomain(BaseModel):
    domain: str

def init_db(db_name):
    print(f"in here, db is {db_name}")
    db = get_db(db_name)
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code VARCHAR(10) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS click_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            ip_address VARCHAR(45),
            user_agent VARCHAR(255),
            referer VARCHAR(255),
            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (link_id) REFERENCES links(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS link_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            tag VARCHAR(255) NOT NULL,
            FOREIGN KEY (link_id) REFERENCES links(id)
        )
    """)
    db.commit()
    db.close()

# Endpoint to create a new short link
@app.post("/links")
def create_link(link: LinkCreate, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO links (original_url, short_code)
        VALUES (?, ?)
    """, (str(link.original_url), link.short_code))
    db.commit()
    return {"message": "Short link created successfully"}

# Endpoint to retrieve all short links
@app.get("/links")
def get_links(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM links")
    links = cursor.fetchall()
    return {"links": links}

# Endpoint to redirect a short link
@app.get("/{short_code}")
def redirect_link(short_code: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, original_url FROM links
        WHERE short_code = ? AND is_active = TRUE
    """, (short_code,))
    link = cursor.fetchone()
    if link:
        print(f"Redirecting to: {link['original_url']}")
        cursor.execute("""
            INSERT INTO click_tracking (link_id, ip_address, user_agent, referer)
            VALUES (?, ?, ?, ?)
        """, (link["id"], "127.0.0.1", "User Agent", "Referer"))
        db.commit()
        return RedirectResponse(url=link["original_url"])
    else:
        raise HTTPException(status_code=404, detail="Short link not found or expired")

# Endpoint to add a tag to a short link
@app.post("/links/{link_id}/tags")
def add_link_tag(link_id: int, tag: LinkTag, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("INSERT INTO link_tags (link_id, tag) VALUES (?, ?)", (link_id, tag.tag))
    db.commit()
    return {"message": "Tag added to the short link successfully"}

# Endpoint to get all tags for a short link
@app.get("/links/{link_id}/tags")
def get_link_tags(link_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT tag FROM link_tags WHERE link_id = ?", (link_id,))
    tags = [row["tag"] for row in cursor.fetchall()]
    return {"tags": tags}

@app.on_event("startup")
async def startup_event():
    init_db("saria.db")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
