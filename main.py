import feedparser
import os
import time
import re
import requests
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium_stealth import stealth
import shutil
import base64
from PIL import Image
import tempfile

# --- برمجة ahmed si (تم الإصلاح النهائي بواسطة Gemini v24.6) ---

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
        print("--- البحث عن منطقة المحتوى باستخدام المحدد 'article.article'...")
        content_area = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.article")))
        images = content_area.find_elements(By.TAG_NAME, "img")
        print(f"--- تم العثور على {len(images)} صورة في منطقة المحتوى.")
        for img in images:
            src = img.get_attribute('src')
            if src and src.startswith('http') and not "data:image" in src:
                if src not in image_urls: image_urls.append(src)
            if len(image_urls) == 2: break
        if image_urls: print(f"--- ✅ تم استخراج {len(image_urls)} روابط صور بنجاح.")
        else: print("--- ⚠️ لم يتم العثور على صور قابلة للاستخراج.")
        return image_urls
    except Exception as e:
        print(f"!!! حدث خطأ أثناء كشط الصور: {e}")
        return []

def download_image(url, path):
    try:
        print(f"--- 📥 جاري تنزيل الصورة من: {url}")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(path, 'wb') as f:
            response.raw.decode_content = True
            shutil.copyfileobj(response.raw, f)
        print(f"--- ✅ تم حفظ الصورة في: {path}")
        return os.path.abspath(path)
    except Exception as e:
        print(f"!!! فشل تنزيل الصورة: {e}")
        return None

def convert_to_png(image_path):
    try:
        print(f"--- 🔄 جاري تحويل الصورة '{image_path}' إلى صيغة PNG...")
        img = Image.open(image_path).convert("RGB")
        png_path = os.path.splitext(image_path)[0] + ".png"
        img.save(png_path, 'png')
        print(f"--- ✅ تم التحويل بنجاح إلى: {png_path}")
        return png_path
    except Exception as e:
        print(f"!!! فشل تحويل الصورة إلى PNG: {e}")
        return None

def copy_image_to_clipboard(driver, image_path):
    print(f"--- 📋 جاري نسخ الصورة '{image_path}' إلى الحافظة...")
    try:
        with open(image_path, "rb") as f: image_data = f.read()
        base64_data = base64.b64encode(image_data).decode('utf-8')
        js_script = """
        async function copyImage(base64) {
            try {
                const byteCharacters = atob(base64);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const blob = new Blob([byteArray], {type: 'image/png'});
                const item = new ClipboardItem({'image/png': blob});
                await navigator.clipboard.write([item]);
                return true;
            } catch (err) {
                console.error('Failed to copy image: ', err);
                return err.message;
            }
        }
        return copyImage(arguments[0]);
        """
        result = driver.execute_script(js_script, base64_data)
        if result is True:
            print("--- ✅ تمت عملية النسخ بنجاح.")
            return True
        else:
            print(f"--- ⚠️ فشلت عملية النسخ. السبب: {result}")
            return False
    except Exception as e:
        print(f"!!! حدث خطأ أثناء نسخ الصورة للحافظة: {e}")
        return False

def rewrite_content_with_gemini(title, content_html, original_link):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None
    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    prompt = f"""
    You are an expert API that returns only JSON. Do not write any conversational text, explanations, or apologies.
    Your entire response must be a single, valid JSON object enclosed in ```json markdown tags.
    **Task:**
    Based on the following recipe data, generate a professional, SEO-optimized Medium article.
    **Input Data:**
    - Title: "{title}"
    - Content Snippet: "{clean_content[:1500]}"
    - Source Link: "{original_link}"
    **JSON Output Structure:**
    Create a JSON object with the following keys:
    - "new_title": A new, engaging, SEO-friendly title (around 8-12 words).
    - "new_html_content": A 600-700 word article in clean, valid HTML. The article must be engaging, well-structured with h2/h3 tags, paragraphs, and lists.
    - "tags": An array of 5 relevant string tags for Medium.
    - "alt_texts": An array of 2 descriptive string alt texts for the images.
    **Crucial Instruction:**
    Within the "new_html_content" value, you MUST insert two image placeholders exactly as written:
    1. `<!-- IMAGE 1 PLACEHOLDER -->` after the introduction.
    2. `<!-- IMAGE 2 PLACEHOLDER -->` in a relevant middle section.
    """

    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 4096}}
    raw_text = ""
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        
        # --- *** الإصلاح النهائي والمؤكد هنا *** ---
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']

        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                clean_json_str = json_match.group(0)
            else:
                raise ValueError("JSON object not found in the Gemini API response.")

        result = json.loads(clean_json_str)
        print("--- ✅ تم استلام مقال كامل من Gemini.")
        return {"title": result.get("new_title", title), "content": result.get("new_html_content", content_html), "tags": result.get("tags", []), "alt_texts": result.get("alt_texts", [])}
    except (requests.exceptions.RequestException, KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        print(f"!!! Gemini Error: {e}")
        print(f"--- Raw Gemini Response: ---\n{raw_text}\n--------------------------")
        return None

def main():
    print("--- بدء تشغيل الروبوت الناشر v24.6 (إصلاح نهائي) ---")
    
    user_data_dir = tempfile.mkdtemp()
    print(f"--- 📂 استخدام مجلد بيانات مؤقت: {user_data_dir}")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920,1080")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    print("--- 🔒 منح إذن الوصول إلى الحافظة للمتصفح...")
    prefs = {"profile.default_content_setting_values.clipboard": 1}
    options.add_experimental_option("prefs", prefs)
    
    driver = None
    image_paths_to_delete = []
    temp_image_dir = ""
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)

        post_to_publish = get_next_post_to_publish()
        if not post_to_publish: 
            print("--- لا توجد مقالات جديدة لنشرها.")
            return
        
        original_title, original_link = post_to_publish.title, post_to_publish.link
        
        scraped_image_urls = scrape_images_from_article(original_link, driver)
        
        original_content_html = ""
        if 'content' in post_to_publish and post_to_publish.content and post_to_publish.content.value:
            original_content_html = post_to_publish.content.value
        elif 'summary' in post_to_publish:
            original_content_html = post_to_publish.summary
            
        rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link)
        
        if not rewritten_data: 
            print("!!! توقف التنفيذ بسبب فشل Gemini في إنشاء المحتوى.")
            return
        
        final_title, generated_html_content, ai_tags = rewritten_data["title"], rewritten_data["content"], rewritten_data.get("tags", [])
        
        png_image_paths = []
        if scraped_image_urls:
            temp_image_dir = tempfile.mkdtemp()
            print(f"--- 🖼️ استخدام مجلد مؤقت للصور: {temp_image_dir}")
            for i, url in enumerate(scraped_image_urls):
                jpg_path = os.path.join(temp_image_dir, f"temp_image_{i}.jpg")
                abs_jpg_path = download_image(url, jpg_path)
                if abs_jpg_path:
                    image_paths_to_delete.append(abs_jpg_path)
                    png_path = convert_to_png(abs_jpg_path)
                    if png_path:
                        png_image_paths.append(png_path)
                        image_paths_to_delete.append(png_path)
        
        sid_cookie, uid_cookie = os.environ.get("MEDIUM_SID_COOKIE"), os.environ.get("MEDIUM_UID_COOKIE")
        if not sid_cookie or not uid_cookie: 
            print("!!! لم يتم العثور على الكوكيز الخاصة بـ Medium.")
            return
        
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": sid_cookie, "domain": ".medium.com"})
        driver.add_cookie({"name": "uid", "value": uid_cookie, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        wait = WebDriverWait(driver, 30)
        actions = ActionChains(driver)
        
        print("--- 4. كتابة العنوان والمحتوى...")
        
        editor_container_selector = "div.is-showEditor"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, editor_container_selector)))
        
        title_field_selector = 'h1[data-testid="editorTitle"]'
        content_field_selector = 'p[data-testid="editorParagraph"]'
        
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, title_field_selector)))
        content_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, content_field_selector)))

        title_field.click()
        actions.send_keys(final_title).perform()
        
        content_field.click()
        
        parts = re.split(r'<!-- IMAGE \d PLACEHOLDER -->', generated_html_content)
        
        for i, part in enumerate(parts):
            if part.strip():
                js_paste_script = "const html = arguments; const blob = new Blob([html], { type: 'text/html' }); const item = new ClipboardItem({ 'text/html': blob }); navigator.clipboard.write([item]);"
                driver.execute_script(js_paste_script, part)
                actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                time.sleep(2)
                
            if i < len(png_image_paths):
                print(f"--- ⬆️ جاري لصق الصورة رقم {i+1} (PNG)...")
                actions.send_keys(Keys.ENTER).perform()
                
                if copy_image_to_clipboard(driver, png_image_paths[i]):
                    time.sleep(1)
                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    
                    print("--- ⏳ انتظار اكتمال رفع الصورة...")
                    upload_wait = WebDriverWait(driver, 60)
                    try:
                        expected_images = i + 1
                        upload_wait.until(
                            lambda d: len(d.find_elements(By.CSS_SELECTOR, f'figure img[src^="https://miro.medium.com"]')) >= expected_images
                        )
                        print(f"--- ✅ الصورة رقم {expected_images} ظهرت في المحرر.")
                    except TimeoutException:
                        print(f"!!! ⚠️ لم يتم التأكد من ظهور الصورة رقم {i+1} في الوقت المحدد.")
                    
                    actions.send_keys(Keys.ARROW_DOWN).send_keys(Keys.ENTER).perform()
                    time.sleep(1)
                else:
                    print(f"!!! تعذر نسخ الصورة {i+1}، سيتم تخطيها.")
                    
        time.sleep(5)
        
        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        driver.execute_script("arguments.click();", publish_button)
        
        print("--- 6. إضافة الوسوم...")
        final_tags = ai_tags[:5] if ai_tags else []
        if final_tags:
            tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Add a topic…"], input[aria-label="Add a topic"]')))
            tags_input.click()
            for tag in final_tags:
                tags_input.send_keys(tag)
                time.sleep(0.5)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")
        
        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        driver.execute_script("arguments.click();", publish_now_button)
        
        print("--- 8. انتظار نهائي...")
        time.sleep(15)
        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! 🎉🎉🎉")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        if driver:
            screenshot_path = "error_screenshot.png"
            page_source_path = "error_page_source.html"
            driver.save_screenshot(screenshot_path)
            with open(page_source_path, "w", encoding="utf-8") as f: f.write(driver.page_source)
            print(f"--- تم حفظ لقطة الشاشة في: {screenshot_path}")
            print(f"--- تم حفظ مصدر الصفحة في: {page_source_path}")
        raise e
    finally:
        print("--- 🧹 جاري تنظيف الملفات المؤقتة...")
        for path in image_paths_to_delete:
            try:
                os.remove(path)
            except OSError:
                pass
        if temp_image_dir and os.path.exists(temp_image_dir):
            shutil.rmtree(temp_image_dir, ignore_errors=True)
            print(f"--- تم حذف مجلد الصور المؤقت: {temp_image_dir}")
            
        if 'driver' in locals() and driver:
            driver.quit()
        
        if 'user_data_dir' in locals() and os.path.exists(user_data_dir):
            shutil.rmtree(user_data_dir, ignore_errors=True)
            print(f"--- تم حذف مجلد البيانات المؤقت: {user_data_dir}")

        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
