# main.py (النسخة المعدلة والنهائية)

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
from selenium.webdriver.common.action_chains import ActionChains
from selenium_stealth import stealth

# --- برمجة ahmed si (تم التطوير بواسطة مساعد Gemini الخبير) ---

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
            if 'href' in enclosure and 'image' in enclosure.get('type', ''): return enclosure['href']
    content_html = ""
    if 'content' in entry and entry.content: content_html = entry.content[0].value
    else: content_html = entry.summary
    match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
    if match: return match.group(1)
    return None

def rewrite_content_with_gemini(title, content_html, original_link):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None
    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    # ملاحظة: تم الإبقاء على تعليمات Gemini كما هي لأنها تنتج الـ Placeholders بشكل صحيح
    prompt = f"""
    You are a professional SEO copywriter for Medium.
    Your task is to take an original recipe title and content, and write a full Medium-style article (around 600 words) optimized for SEO and engagement.
    **Original Data:**
    - Original Title: "{title}"
    - Original Content Snippet: "{clean_content[:1500]}"
    - Link to the full recipe: "{original_link}"
    **Article Requirements:**
    1.  **Title:** Create a new engaging, SEO-friendly title.
    2.  **Article Body (HTML Format):** Write a 600-700 word article in clean HTML. It is crucial that you insert two image placeholders exactly as written below:
        - `<!-- IMAGE 1 PLACEHOLDER -->` after the intro.
        - `<!-- IMAGE 2 PLACEHOLDER -->` before a relevant section (like a listicle).
    3.  **Smart Closing:** End with a wrap-up, a CTA to the original link, and a question for readers.
    **Output Format:**
    Return ONLY a valid JSON object with the keys: "new_title", "new_html_content", "tags", and "alt_texts".
    """
    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 4096}}
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        # تنظيف الرد للعثور على JSON صحيح
        json_str_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_str_match:
            json_str = json_str_match.group(1)
        else:
            json_str = raw_text # fallback
        
        result = json.loads(json_str)
        print("--- ✅ تم استلام مقال كامل من Gemini.")
        return {"title": result.get("new_title", title), "content": result.get("new_html_content", content_html), "tags": result.get("tags", []), "alt_texts": result.get("alt_texts", [])}
    except Exception as e:
        print(f"!!! حدث خطأ فادح أثناء التواصل مع Gemini: {e}")
        return None

# --- الدالة الجديدة والمحورية لحل مشكلة الصور ---
def insert_images_natively(driver, wait, image_url, alt_texts):
    print("--- 🏞️ بدء عملية إدراج الصور بالطريقة الموثوقة ---")
    placeholders = ["<!-- IMAGE 1 PLACEHOLDER -->", "<!-- IMAGE 2 PLACEHOLDER -->"]
    
    for i, placeholder_text in enumerate(placeholders):
        try:
            # استخدام XPath للبحث عن العنصر الذي يحتوي على نص الـ Placeholder
            # هذا أكثر استقراراً من البحث عن النص فقط
            placeholder_element = wait.until(
                EC.presence_of_element_located((By.XPATH, f"//p[contains(text(), 'IMAGE {i+1} PLACEHOLDER')]"))
            )
            print(f"--- تم العثور على placeholder #{i+1}")

            # ننزل إلى العنصر ليكون مرئياً ونضغط عليه
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", placeholder_element)
            time.sleep(1)
            placeholder_element.click()

            # نمسح نص الـ Placeholder ونضغط Enter لإنشاء سطر جديد
            placeholder_element.clear()
            time.sleep(0.5)
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(1)

            # الآن نحن على سطر فارغ وجاهز. نظهر زر الإضافة (+)
            plus_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="open-embed-bar"]')))
            plus_button.click()
            time.sleep(1)

            # نختار أيقونة الكاميرا التي تفتح خيار "Add an image"
            camera_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="embed-image"]')))
            camera_button.click()
            time.sleep(1)

            # نلصق رابط الصورة في الحقل المخصص
            url_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Paste an image link…"]')))
            url_input.send_keys(image_url)
            url_input.send_keys(Keys.ENTER)
            
            # ننتظر حتى يقوم Medium بمعالجة الصورة وظهورها (العلامة هي وجود div.graf-image)
            print(f"--- جاري معالجة الصورة #{i+1}...")
            wait.until(EC.presence_of_element_located((By.XPATH, f"(//div[contains(@class, 'graf--figure') ])[{i+1}]")))
            time.sleep(5) # انتظار إضافي لضمان اكتمال التحميل والعرض
            print(f"--- ✅ تمت معالجة الصورة #{i+1} بنجاح.")

        except Exception as e:
            print(f"!!! حدث خطأ أثناء إدراج الصورة #{i+1}: {e}")
            # في حال الفشل، نطبع لقطة شاشة للمساعدة في التشخيص
            driver.save_screenshot(f"error_image_{i+1}.png")
            continue

def main():
    print("--- بدء تشغيل الروبوت الناشر v28 (الحل الموثوق للصور) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

    original_title = post_to_publish.title
    original_link = post_to_publish.link
    image_url = extract_image_url_from_entry(post_to_publish)
    if image_url:
        print(f"--- 🖼️ تم العثور على رابط الصورة: {image_url}")
    else:
        print("--- ⚠️ لم يتم العثور على رابط صورة في RSS. سيتم النشر بدون صور.")
    
    original_content_html = post_to_publish.summary
    if 'content' in post_to_publish and post_to_publish.content:
        original_content_html = post_to_publish.content[0].value

    rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link)
    
    if not rewritten_data:
        print("--- فشل التواصل مع Gemini. سيتم استخدام المحتوى الأصلي.")
        final_title = original_title
        generated_html_content = original_content_html
        ai_tags = []
        ai_alt_texts = []
    else:
        final_title = rewritten_data["title"]
        generated_html_content = rewritten_data["content"]
        ai_tags = rewritten_data.get("tags", [])
        ai_alt_texts = rewritten_data.get("alt_texts", [])
    
    # المحتوى الآن لا يحتوي على وسوم <img>، فقط الـ placeholders
    full_html_content = generated_html_content

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

        print("--- 4. كتابة العنوان ولصق المحتوى (بدون الصور)...")
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'textarea[placeholder="Title"]')))
        title_field.send_keys(final_title)

        # الضغط على حقل المحتوى للبدء
        story_field_placeholder = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-placeholder-string="Tell your story…"]')))
        story_field_placeholder.click()
        
        # استخدام طريقة اللصق الموثوقة
        js_script = "const html = arguments[0]; const blob = new Blob([html], { type: 'text/html' }); const item = new ClipboardItem({ 'text/html': blob }); navigator.clipboard.write([item]);"
        driver.execute_script(js_script, full_html_content)
        
        # نرسل أمر اللصق إلى العنصر النشط حالياً في الصفحة
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        time.sleep(5)
        print("--- تم لصق المحتوى النصي بنجاح.")

        # --- الخطوة الجديدة والحاسمة: إدراج الصور بالطريقة الصحيحة ---
        if image_url:
            insert_images_natively(driver, wait, image_url, ai_alt_texts)

        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Publish']")))
        publish_button.click()
        
        print("--- 6. إضافة الوسوم...")
        # استخدام محدد أكثر دقة
        tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.tags-input input')))
        
        final_tags = ai_tags[:5] if ai_tags else []
        if final_tags:
            for tag in final_tags:
                tags_input.send_keys(tag)
                time.sleep(0.5)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")
        else:
            print("--- لا توجد وسوم لإضافتها.")
            
        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Publish now']")))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)
        
        print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
        time.sleep(15)
        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح مع الصور! 🎉🎉🎉")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        driver.save_screenshot("error_screenshot.png")
        with open("error_page_source.html", "w", encoding="utf-8") as f: f.write(driver.page_source)
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
