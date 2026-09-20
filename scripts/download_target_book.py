import os
import json
import time
import urllib.request
import re
from html import unescape

WORK_ID = 618037
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "target", "chapters")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHAPTERS = [
    {"num": 1, "id": 5899546, "title": "Глава 01."},
    {"num": 2, "id": 5899593, "title": "Глава 02."},
    {"num": 3, "id": 5909219, "title": "Глава 03."},
    {"num": 4, "id": 5921624, "title": "Глава 04."},
    {"num": 5, "id": 5933148, "title": "Глава 05."},
    {"num": 6, "id": 5947388, "title": "Глава 06."},
    {"num": 7, "id": 5957253, "title": "Глава 07."},
    {"num": 8, "id": 5971194, "title": "Глава 08."},
    {"num": 9, "id": 5985806, "title": "Глава 09."},
    {"num": 10, "id": 5996201, "title": "Глава 10."},
    {"num": 11, "id": 6011039, "title": "Глава 11."},
    {"num": 12, "id": 6029303, "title": "Глава 12."},
    {"num": 13, "id": 6042445, "title": "Глава 13."},
    {"num": 14, "id": 6057762, "title": "Глава 14."},
    {"num": 15, "id": 6073287, "title": "Глава 15."},
    {"num": 16, "id": 6091783, "title": "Глава 16."},
    {"num": 17, "id": 6101000, "title": "Глава 17."},
    {"num": 18, "id": 6115990, "title": "Глава 18."},
    {"num": 19, "id": 6130394, "title": "Глава 19."},
    {"num": 20, "id": 6146025, "title": "Глава 20."},
    {"num": 21, "id": 6160901, "title": "Глава 21."},
    {"num": 22, "id": 6180251, "title": "Глава 22."},
    {"num": 23, "id": 6203209, "title": "Глава 23."},
]

def clean_html(raw_html: str) -> str:
    """Converts HTML paragraphs to clean formatted plain text."""
    text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', raw_html, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def decrypt_text(cipher_text: str, secret: str) -> str:
    """Decrypts Author.Today XOR encrypted text."""
    if not secret:
        return cipher_text
    key = secret[::-1] + "@_@"
    k_len = len(key)
    plain_chars = [chr(ord(c) ^ ord(key[i % k_len])) for i, c in enumerate(cipher_text)]
    return "".join(plain_chars)

def download_chapter(ch_info):
    ch_id = ch_info["id"]
    ch_num = ch_info["num"]
    title = ch_info["title"]
    
    txt_filename = f"chapter_{ch_num:02d}.txt"
    txt_path = os.path.join(OUTPUT_DIR, txt_filename)
    
    url = f"https://author.today/reader/{WORK_ID}/chapter?id={ch_id}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'https://author.today/reader/{WORK_ID}/{ch_id}',
        'Cookie': 'AdultUser=true'
    })
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        secret = resp.headers.get("Reader-Secret", "")
        res = json.loads(resp.read().decode('utf-8'))
        if not res.get("isSuccessful") or not res.get("data"):
            raise RuntimeError(f"Failed to fetch chapter {ch_num}: {res}")
            
        raw_text = res["data"]["text"]
        decrypted_html = decrypt_text(raw_text, secret)
        clean_text = clean_html(decrypted_html)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n" + clean_text)
            
        print(f"Decrypted Chapter {ch_num:02d} ({title}): {len(clean_text)} chars -> {txt_filename}")
        return {
            "num": ch_num,
            "id": ch_id,
            "title": title,
            "char_count": len(clean_text),
            "file": txt_filename
        }

def main():
    print(f"Starting download and decryption of {len(CHAPTERS)} chapters for work {WORK_ID}...")
    manifest = {
        "work_id": WORK_ID,
        "title": "Система Абсолютного З.Л.А.",
        "author": "N.B.",
        "url": f"https://author.today/work/{WORK_ID}",
        "total_chapters": len(CHAPTERS),
        "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chapters": []
    }
    
    total_chars = 0
    for ch in CHAPTERS:
        info = download_chapter(ch)
        manifest["chapters"].append(info)
        total_chars += info["char_count"]
        time.sleep(0.4)
        
    manifest["total_chars"] = total_chars
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        
    print(f"\nAll {len(CHAPTERS)} chapters successfully decrypted and saved to {OUTPUT_DIR}")
    print(f"Total clean characters: {total_chars:,} chars (~{total_chars/40000:.2f} a.l.)")

if __name__ == "__main__":
    main()
