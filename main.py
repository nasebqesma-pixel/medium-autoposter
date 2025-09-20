import feedparser
import os
import time
import re
import requests
import json
import uuid # لإعطاء اسم فريد للملف
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# --- برمجة ahmed si ---

RSS_URL = "https://Fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE): return set()
    with open(POSTED_LINKS_FILE, "r", encoding='utf-8') as f: return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a", encoding='utf-8') as f: f.write(link + "\n")

def get_next_post_to_publish():
    print(f"--- 1. البحث عن مقالات في: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries: return None
    print(f"--- تم العثور على {len(feed.entries)} مقالات.")
    posted_links = get_posted_links()
    for entry in reversed(feed.entries):
        if entry.link not in posted_links:
            print(f">>> تم تحديد المقال: {entry.title}")
            return entry
    return None

def extract_image_url_from_entry(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media and media.get('medium') == 'image': return media['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'href' in enclosure and 'image' in enclosure.get('type', ''): return enclosure.href
    content_html = ""
    if 'content' in entry and entry.content: content_html = entry.content[0].value
    else: content_html = entry.summary
    match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
    if match: return match.group(1)
    return None

# *** وظيفة جديدة: تنزيل الصورة ***
def download_image(url):
    """يقوم بتنزيل صورة من رابط معين وحفظها محليًا."""
    try:
        temp_dir = os.path.join(os.getcwd(), 'temp_images')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        temp_image_path = os.path.join(temp_dir, f"{uuid.uuid4()}.jpeg")
        print(f"--- 🖼️ جاري تنزيل الصورة من: {url}")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(temp_image_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"--- ✅ تم تنزيل الصورة بنجاح إلى: {temp_image_path}")
        return temp_image_path
    except Exception as e:
        print(f"!!! حدث خطأ أثناء تنزيل الصورة: {e}")
        return None

def rewrite_content_with_gemini(title, content_html, original_link, image_url):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None
    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    prompt = f"""
    You are a professional SEO copywriter for Medium.
    Your task is to take an original recipe title and content, and write a full Medium-style article (around 600 words) optimized for SEO, engagement, and backlinks.
    **Original Data:**
    - Original Title: "{title}"
    - Original Content Snippet: "{clean_content[:1500]}"
    - Link to the full recipe: "{original_link}"
    - Available Image URL: "{image_url}"
    **Article Requirements:**
    1.  **Focus Keyword:** Identify the main focus keyword from the original title.
    2.  **Title:** Create a new title using the Hybrid Headline strategy...
    3.  **Article Body (JSON Format):**
        - Write a 600-700 word article.
        - The article body must be a plain text string without any HTML tags.
        - **Image Placement:** Do not include image placeholders or HTML in your response. We will handle image placement separately.
        - (Other requirements remain the same...)
    4.  **Smart Closing Method...**
    **Output Format:**
    Return ONLY a valid JSON object with the keys: "new_title", "new_body_content", "tags", and "alt_texts".
    ...
    """
    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 4096}}
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(0)
            result = json.loads(clean_json_str)
            print("--- ✅ تم استلام مقال كامل من Gemini.")
            return {"title": result.get("new_title", title), "content": result.get("new_body_content", clean_content), "tags": result.get("tags", []), "alt_texts": result.get("alt_texts", [])}
        else:
            raise ValueError("لم يتم العثور على صيغة JSON في رد Gemini.")
    except Exception as e:
        print(f"!!! حدث خطأ فادح أثناء التواصل مع Gemini: {e}")
        return None

def main():
    temp_image_path = None
    try:
        print("--- بدء تشغيل الروبوت الناشر v21.3 (مع تشخيص الصور) ---")
        post_to_publish = get_next_post_to_publish()
        if not post_to_publish:
            print(">>> النتيجة: لا توجد مقالات جديدة.")
            return

        original_title = post_to_publish.title
        original_link = post_to_publish.link
        
        # --- **تغيير هنا**: تنزيل الصورة قبل التواصل مع Gemini ---
        image_url = extract_image_url_from_entry(post_to_publish)
        if image_url:
            temp_image_path = download_image(image_url)
            if not temp_image_path:
                print("--- ⚠️ فشل تنزيل الصورة، سيتم تجاهل الصورة.")
        else:
            print("--- ⚠️ لم يتم العثور على رابط صورة في RSS لهذا المقال.")
        
        original_content_html = ""
        if 'content' in post_to_publish and post_to_publish.content:
            original_content_html = post_to_publish.content[0].value
        else:
            original_content_html = post_to_publish.summary

        rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link, image_url)
        
        if rewritten_data:
            final_title = rewritten_data["title"]
            generated_body_content = rewritten_data["content"]
            ai_tags = rewritten_data.get("tags", [])
            ai_alt_texts = rewritten_data.get("alt_texts", [])
            full_text_content = generated_body_content
            print("--- ✅ تم تجهيز المقال بنجاح.")
        else:
            print("--- سيتم استخدام المحتوى الأصلي بسبب فشل Gemini.")
            final_title = original_title
            ai_tags = []
            full_text_content = re.sub('<[^<]+?>', ' ', original_content_html)

        sid_cookie = os.environ.get("MEDIUM_SID_COOKIE")
        uid_cookie = os.environ.get("MEDIUM_UID_COOKIE")
        if not sid_cookie or not uid_cookie:
            print("!!! خطأ: لم يتم العثور على الكوكيز.")
            return

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("window-size=1920,1080")

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)

        try:
            print("--- 2. إعداد الجلسة...")
            driver.get("https://medium.com/")
            driver.add_cookie({"name": "sid", "value": sid_cookie, "domain": ".medium.com"})
            driver.add_cookie({"name": "uid", "value": uid_cookie, "domain": ".medium.com"})
            
            print("--- 3. الانتقال إلى محرر المقالات...")
            driver.get("https://medium.com/new-story")

            wait = WebDriverWait(driver, 30)

            print("--- 4. كتابة العنوان والمحتوى...")
            title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
            title_field.click()
            title_field.send_keys(final_title)

            story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
            story_field.click()

            # *** التعديل هنا: رفع الصورة ثم لصق النص ***
            if temp_image_path and os.path.exists(temp_image_path):
                print("--- 🖼️ جاري رفع الصورة...")
                
                # إظهار زر الإضافة
                add_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label="Add an image"]')))
                add_button.click()
                time.sleep(1)

                # البحث عن input type="file" المخفي
                # Note: Medium قد يغير هذا الـ selector
                file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"][accept*="image/"]')))
                
                # إرسال مسار الملف إلى الـ input
                file_input.send_keys(temp_image_path)
                time.sleep(10) # إعطاء وقت كافٍ للرفع
                print("--- ✅ تم رفع الصورة بنجاح.")
            
            # لصق نص المقال
            story_field.send_keys(full_text_content)
            
            print("--- 5. بدء عملية النشر...")
            publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
            publish_button.click()

            print("--- 6. إضافة الوسوم المتاحة...")
            final_tags = ai_tags[:5] if ai_tags else []
            
            if final_tags:
                tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
                tags_input.click()
                for tag in final_tags:
                    tags_input.send_keys(tag)
                    time.sleep(0.5)
                    tags_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")
            else:
                print("--- لا توجد وسوم لإضافتها.")

            print("--- 7. إرسال أمر النشر النهائي...")
            publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
            driver.execute_script("arguments[0].click();", publish_now_button)
            
            print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
            time.sleep(15)

            add_posted_link(post_to_publish.link)
            print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! 🎉🎉🎉")

        except Exception as e:
            print(f"!!! حدث خطأ فادح: {e}")
            driver.save_screenshot("error_screenshot.png")
            with open("error_page_source.html", "w", encoding="utf-8") as f: f.write(driver.page_source)
            raise e
        finally:
            driver.quit()
            print("--- تم إغلاق الروبوت ---")
            if temp_image_path and os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print("--- تم حذف ملف الصورة المؤقت بنجاح.")

if __name__ == "__main__":
    main()
