import feedparser
import os
import time
import re
import requests
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# --- برمجة ahmed si (تم التعديل بآلية رفع الصور بواسطة Gemini v22.6) ---

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

def scrape_images_from_article(url, driver):
    print(f"--- 🖼️ جاري كشط الصور من الرابط الأصلي: {url}")
    image_urls = []
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        content_area = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.article")))
        images = content_area.find_elements(By.TAG_NAME, "img")
        print(f"--- تم العثور على {len(images)} صورة في منطقة المحتوى.")
        for img in images:
            src = img.get_attribute('src')
            if src and src.startswith('http') and not "data:image" in src:
                if src not in image_urls:
                    image_urls.append(src)
            if len(image_urls) == 2:
                break
        if image_urls:
            print(f"--- ✅ تم استخراج {len(image_urls)} روابط صور بنجاح.")
        else:
            print("--- ⚠️ لم يتم العثور على صور قابلة للاستخراج من الصفحة.")
        return image_urls
    except Exception as e:
        print(f"!!! حدث خطأ أثناء كشط الصور: {e}")
        return []

def rewrite_content_with_gemini(title, content_html, original_link, image_urls):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None
    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    prompt = f"""
    You are a professional SEO copywriter for Medium. Your task is to take an original recipe title and content, and write a full Medium-style article (around 600 words) optimized for SEO, engagement, and backlinks.
    **Original Data:**
    - Original Title: "{title}"
    - Original Content Snippet: "{clean_content[:1500]}"
    - Link to the full recipe: "{original_link}"
    - Available Image URLs: "{', '.join(image_urls) if image_urls else 'None'}"
    **Article Requirements:**
    1.  **Title:** Create a new, SEO-optimized title using the Hybrid Headline strategy.
    2.  **Article Body (HTML Format):**
        - Write a 600-700 word article in clean HTML.
        - **Image Placement:** Crucially, you MUST insert two image placeholders exactly as written below:
            - `<!-- IMAGE 1 PLACEHOLDER -->` after the intro.
            - `<!-- IMAGE 2 PLACEHOLDER -->` before the listicle section or a relevant paragraph.
            Do not add your own `<img>` tags.
    3.  **Smart Closing Method:** End with a compelling call-to-action that encourages readers to visit the original recipe link for detailed instructions.
    **Output Format:**
    Return ONLY a valid JSON object with the keys: "new_title", "new_html_content", "tags", and "alt_texts". "alt_texts" should be an array of two descriptive strings for the images.
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
            return {"title": result.get("new_title", title), "content": result.get("new_html_content", content_html), "tags": result.get("tags", []), "alt_texts": result.get("alt_texts", ["Image of the dish", "Another view of the recipe"])}
        else:
            raise ValueError("لم يتم العثور على صيغة JSON في رد Gemini.")
    except Exception as e:
        print(f"!!! حدث خطأ فادح أثناء التواصل مع Gemini: {e}")
        return None

# --- دالة جديدة لتحميل الصورة ---
def download_image(url, filename):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"!!! فشل تحميل الصورة {url}: {e}")
        return False

# --- دالة مساعدة للصق محتوى HTML ---
def paste_html(driver, html_content):
    if not html_content.strip(): return
    js_script = "const html = arguments[0]; const sel = window.getSelection(); if (sel.rangeCount > 0) { const range = sel.getRangeAt(0); range.deleteContents(); const el = document.createElement('div'); el.innerHTML = html; const frag = document.createDocumentFragment(); let node; while ((node = el.firstChild)) { frag.appendChild(node); } range.insertNode(frag); }"
    driver.execute_script(js_script, html_content)

def main():
    print("--- بدء تشغيل الروبوت الناشر v22.6 (مع رفع الصور) ---")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920,1080")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    
    downloaded_files = [] # قائمة لتتبع الملفات المؤقتة
    try:
        post_to_publish = get_next_post_to_publish()
        if not post_to_publish:
            print(">>> النتيجة: لا توجد مقالات جديدة لنشرها.")
            return

        original_title = post_to_publish.title
        original_link = post_to_publish.link
        scraped_image_urls = scrape_images_from_article(original_link, driver)
        
        original_content_html = ""
        if 'content' in post_to_publish and post_to_publish.content:
            original_content_html = post_to_publish.content[0].value
        else:
            original_content_html = post_to_publish.summary

        rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link, scraped_image_urls)
        
        if not rewritten_data:
            print("!!! فشل Gemini، لا يمكن المتابعة.")
            return

        final_title = rewritten_data["title"]
        generated_html_content = rewritten_data["content"]
        ai_tags = rewritten_data.get("tags", [])
        
        # --- تقسيم المحتوى حسب أماكن الصور ---
        parts = re.split(r'<!-- IMAGE (?:1|2) PLACEHOLDER -->', generated_html_content)
        part1 = parts[0] if len(parts) > 0 else ""
        part2 = parts[1] if len(parts) > 1 else ""
        part3 = parts[2] if len(parts) > 2 else ""

        sid_cookie = os.environ.get("MEDIUM_SID_COOKIE")
        uid_cookie = os.environ.get("MEDIUM_UID_COOKIE")
        if not sid_cookie or not uid_cookie:
            print("!!! خطأ: لم يتم العثور على الكوكيز.")
            return

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
        
        # --- آلية النشر الجديدة ---
        paste_html(driver, part1)
        story_field.send_keys(Keys.ENTER)

        # رفع الصورة الأولى
        if scraped_image_urls:
            print("--- 📥 تحميل ورفع الصورة الأولى...")
            image_path = "temp_image_1.jpg"
            if download_image(scraped_image_urls[0], image_path):
                downloaded_files.append(image_path)
                file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
                file_input.send_keys(os.path.abspath(image_path))
                # انتظر حتى يتم رفع الصورة (ظهورها في المحرر)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src^="https://miro.medium.com"]')))
                print("--- ✅ تم رفع الصورة الأولى.")
                time.sleep(3) # انتظر قليلاً للتأكد
        
        story_field.send_keys(Keys.ENTER)
        paste_html(driver, part2)
        story_field.send_keys(Keys.ENTER)

        # رفع الصورة الثانية
        if len(scraped_image_urls) > 1:
            print("--- 📥 تحميل ورفع الصورة الثانية...")
            image_path = "temp_image_2.jpg"
            if download_image(scraped_image_urls[1], image_path):
                downloaded_files.append(image_path)
                file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
                file_input.send_keys(os.path.abspath(image_path))
                # انتظر رفع الصورة الثانية
                wait.until(EC.presence_of_element_located((By.XPATH, '(//img[starts-with(@src, "https://miro.medium.com")])[2]')))
                print("--- ✅ تم رفع الصورة الثانية.")
                time.sleep(3)
        
        story_field.send_keys(Keys.ENTER)
        paste_html(driver, part3)
        time.sleep(5)

        # --- استكمال عملية النشر كالمعتاد ---
        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم المتاحة...")
        if ai_tags:
            tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
            tags_input.click()
            for tag in ai_tags[:5]:
                tags_input.send_keys(tag)
                time.sleep(0.5)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(ai_tags[:5])}")
        else:
            print("--- لا توجد وسوم لإضافتها.")

        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2)
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
        # --- تنظيف الملفات المؤقتة ---
        for f in downloaded_files:
            if os.path.exists(f):
                os.remove(f)
                print(f"--- تم حذف الملف المؤقت: {f}")
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
