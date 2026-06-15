import asyncio
from app.services.import_pandamall_scraper import scrape_pandamall_for_import
import json

async def main():
    try:
        raw, pd, warnings = scrape_pandamall_for_import("https://pandamall.vn/1688/detail/935969699245")
        print("RAW META:", raw.get("title"))
        print("DETAIL IMAGES:", len(raw.get("detail_images", [])))
        print("GALLERY IMAGES:", len(raw.get("gallery", [])), raw.get("gallery", []))
        print("INFO TEXTS:", len(raw.get("info_texts", [])))
        print("WARNINGS:", warnings)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
