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

# --- برمجة ahmed si - النسخة النهائية v26 مع Selenium للكشط ---

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
    """استخراج أول صورة من RSS feed"""
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

def scrape_images_with_selenium(article_url):
    """كشط الصور باستخدام Selenium (يشغل JavaScript)"""
    print(f"--- 🔍 كشط الصور بـ Selenium من: {article_url}")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # إضافة stealth للتخفي
    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True)
    
    images = []
    
    try:
        print("    ⏳ تحميل الصفحة...")
        driver.get(article_url)
        
        # انتظار تحميل الصور
        time.sleep(3)
        
        # محاولة التمرير لتحميل الصور الكسولة
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        print("    🔎 البحث عن الصور في الصفحة...")
        
        # البحث عن كل عناصر img
        img_elements = driver.find_elements(By.TAG_NAME, "img")
        
        for img in img_elements:
            try:
                # جرب الحصول على src
                src = img.get_attribute("src")
                if not src:
                    src = img.get_attribute("data-src")
                if not src:
                    src = img.get_attribute("data-lazy-src")
                if not src:
                    src = img.get_attribute("data-original")
                
                # أيضاً جرب currentSrc للصور التي تم تحميلها
                if not src:
                    src = driver.execute_script("return arguments[0].currentSrc;", img)
                
                if src and ("/assets/images/" in src or "fastyummyfood" in src.lower()):
                    # تنظيف الرابط
                    clean_url = src.split('?')[0]
                    
                    # تحويل إلى رابط مطلق إذا لزم
                    if not clean_url.startswith("http"):
                        if clean_url.startswith("//"):
                            clean_url = "https:" + clean_url
                        elif clean_url.startswith("/"):
                            from urllib.parse import urljoin
                            clean_url = urljoin(article_url, clean_url)
                    
                    # تجنب التكرار والصور الصغيرة
                    if clean_url not in images and not any(x in clean_url.lower() for x in ['logo', 'icon', 'avatar']):
                        images.append(clean_url)
                        print(f"    ✓ وجدت صورة: {clean_url[:60]}...")
                        
            except Exception as e:
                continue
        
        # البحث في article tag بشكل خاص
        try:
            article_element = driver.find_element(By.TAG_NAME, "article")
            # البحث عن صور background في CSS
            all_elements = article_element.find_elements(By.XPATH, ".//*")
            for elem in all_elements:
                try:
                    bg_image = driver.execute_script("""
                        var style = window.getComputedStyle(arguments[0]);
                        var bg = style.getPropertyValue('background-image');
                        if (bg && bg !== 'none') {
                            var match = bg.match(/url\KATEX_INLINE_OPEN['\"]?([^'\"\KATEX_INLINE_CLOSE]+)['\"]?\KATEX_INLINE_CLOSE/);
                            return match ? match[1] : null;
                        }
                        return null;
                    """, elem)
                    
                    if bg_image and "/assets/images/" in bg_image and bg_image not in images:
                        images.append(bg_image)
                        print(f"    ✓ وجدت صورة خلفية: {bg_image[:60]}...")
                except:
                    continue
        except:
            pass
        
        # إذا لم نجد صور، جرب البحث في source tags (للـ picture elements)
        if len(images) < 2:
            source_elements = driver.find_elements(By.TAG_NAME, "source")
            for source in source_elements:
                try:
                    srcset = source.get_attribute("srcset")
                    if srcset:
                        # استخرج أول رابط من srcset
                        first_url = re.search(r'([^\s,]+)', srcset)
                        if first_url:
                            url = first_url.group(1)
                            if "/assets/images/" in url and url not in images:
                                if not url.startswith("http"):
                                    from urllib.parse import urljoin
                                    url = urljoin(article_url, url)
                                images.append(url)
                                print(f"    ✓ وجدت صورة من source: {url[:60]}...")
                except:
                    continue
        
        print(f"--- ✅ تم العثور على {len(images)} صورة باستخدام Selenium")
        
    except Exception as e:
        print(f"--- ⚠️ خطأ في Selenium: {e}")
    finally:
        driver.quit()
    
    return images

def get_best_images_for_article(article_url, rss_image=None):
    """الحصول على أفضل صورتين للمقال"""
    # استخدام Selenium للكشط
    scraped_images = scrape_images_with_selenium(article_url)
    
    all_images = []
    
    # إضافة الصور المكشوطة أولاً (لها الأولوية)
    all_images.extend(scraped_images)
    
    # إضافة صورة RSS كخيار احتياطي
    if rss_image and rss_image not in all_images:
        all_images.append(rss_image)
    
    # إزالة التكرارات
    unique_images = []
    seen = set()
    for img in all_images:
        if img not in seen:
            unique_images.append(img)
            seen.add(img)
    
    # اختيار صورتين مختلفتين
    if len(unique_images) >= 2:
        image1 = unique_images[0]
        # محاولة الحصول على صورة مختلفة
        if len(unique_images) >= 3:
            image2 = unique_images[2]  # تخطي الثانية للتنوع
        else:
            image2 = unique_images[1]
    elif len(unique_images) == 1:
        image1 = image2 = unique_images[0]
    else:
        image1 = image2 = None
    
    return image1, image2

def rewrite_content_with_gemini(title, content_html, original_link):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None

    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    
    prompt = """
    You are a professional SEO copywriter for Medium.
    Your task is to rewrite a recipe article for maximum engagement and SEO.

    **Original Data:**
    - Original Title: "%s"
    - Original Content: "%s"
    - Link to full recipe: "%s"

    **Requirements:**
    1. **New Title:** Create an engaging, SEO-optimized title (60-70 characters)
    2. **Article Body:** Write 600-700 words in clean HTML format
       - Start with a compelling introduction
       - Include practical tips and insights
       - Use headers (h2, h3) for structure
       - Add numbered or bulleted lists where appropriate
       - **IMPORTANT**: Use ONLY simple HTML tags (p, h2, h3, ul, ol, li, strong, em, br)
       - **DO NOT** use img, figure, or complex tags
       - Insert these EXACT placeholders AS WRITTEN:
         * INSERT_IMAGE_1_HERE (after the introduction paragraph)
         * INSERT_IMAGE_2_HERE (in the middle section of the article)
    3. **Call to Action:** End with a natural link to the original recipe
    4. **Tags:** Suggest 5 relevant Medium tags

    **Output Format:**
    Return ONLY a valid JSON object with these keys:
    - "new_title": The new title
    - "new_html_content": The HTML content with INSERT_IMAGE_1_HERE and INSERT_IMAGE_2_HERE placeholders
    - "tags": Array of 5 tags
    """ % (title, clean_content[:1500], original_link)
    
    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.7}
    }
    
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(0)
            result = json.loads(clean_json_str)
            print("--- ✅ تم استلام مقال محسّن من Gemini.")
            return {
                "title": result.get("new_title", title),
                "content": result.get("new_html_content", content_html),
                "tags": result.get("tags", [])
            }
    except Exception as e:
        print(f"!!! خطأ في Gemini: {e}")
        return None

def prepare_html_with_multiple_images(content_html, image1, image2, original_link):
    """إعداد HTML النهائي مع صورتين"""
    
    print("--- 🎨 إعداد المحتوى النهائي مع الصور...")
    
    # إعداد HTML للصورة الأولى
    if image1:
        image1_html = f'<img src="{image1}" alt="Recipe preparation">'
        image1_with_caption = f'{image1_html}<p><em>Step-by-step preparation process</em></p>'
    else:
        image1_with_caption = ""
    
    # إعداد HTML للصورة الثانية  
    if image2:
        if image2 == image1:
            caption2 = "Another view of this delicious recipe"
        else:
            caption2 = "The delicious final result!"
        image2_html = f'<img src="{image2}" alt="Final dish">'
        image2_with_caption = f'{image2_html}<p><em>{caption2}</em></p>'
    else:
        image2_with_caption = ""
    
    # استبدال العلامات
    content_html = content_html.replace("INSERT_IMAGE_1_HERE", image1_with_caption)
    content_html = content_html.replace("INSERT_IMAGE_2_HERE", image2_with_caption)
    
    # إضافة رابط المصدر
    site_name = "Fastyummyfood.com"
    call_to_action = f'<br><p><strong>For the complete recipe with detailed instructions, visit <a href="{original_link}" rel="noopener" target="_blank">{site_name}</a>.</strong></p>'
    
    return content_html + call_to_action

def main():
    print("--- بدء تشغيل الروبوت الناشر v26 (مع Selenium للكشط) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

    original_title = post_to_publish.title
    original_link = post_to_publish.link
    
    # استخراج صورة RSS
    rss_image = extract_image_url_from_entry(post_to_publish)
    if rss_image:
        print(f"--- 📷 صورة RSS: {rss_image[:80]}...")
    
    # الحصول على الصور من المقال
    image1, image2 = get_best_images_for_article(original_link, rss_image)
    
    if image1:
        print(f"--- 🖼️ الصورة الأولى للنشر: {image1[:80]}...")
    if image2:
        print(f"--- 🖼️ الصورة الثانية للنشر: {image2[:80]}...")
    
    if not image1:
        print("--- ⚠️ لم يتم العثور على أي صور!")
    
    # الحصول على المحتوى الأصلي
    original_content_html = ""
    if 'content' in post_to_publish and post_to_publish.content:
        original_content_html = post_to_publish.content[0].value
    else:
        original_content_html = post_to_publish.summary

    # تحسين المحتوى باستخدام Gemini
    rewritten_data = rewrite_content_with_gemini(
        original_title, original_content_html, original_link
    )
    
    if rewritten_data:
        final_title = rewritten_data["title"]
        ai_content = rewritten_data["content"]
        ai_tags = rewritten_data.get("tags", [])
        
        # إعداد المحتوى النهائي
        full_html_content = prepare_html_with_multiple_images(
            ai_content, image1, image2, original_link
        )
        print("--- ✅ تم إعداد المحتوى المُحسّن مع الصور.")
    else:
        print("--- ⚠️ سيتم استخدام المحتوى الأصلي.")
        final_title = original_title
        ai_tags = []
        
        if image1:
            image1_html = f'<img src="{image1}">'
        else:
            image1_html = ""
        
        if image2 and image2 != image1:
            image2_html = f'<br><img src="{image2}">'
        else:
            image2_html = ""
        
        link_html = f'<br><p><em>For the full recipe, visit <a href="{original_link}" rel="noopener" target="_blank">Fastyummyfood.com</a>.</em></p>'
        full_html_content = image1_html + original_content_html + image2_html + link_html

    # --- النشر على Medium ---
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

    stealth(driver, 
            languages=["en-US", "en"], 
            vendor="Google Inc.", 
            platform="Win32", 
            webgl_vendor="Intel Inc.", 
            renderer="Intel Iris OpenGL Engine", 
            fix_hairline=True)
    
    try:
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": sid_cookie, "domain": ".medium.com"})
        driver.add_cookie({"name": "uid", "value": uid_cookie, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        
        wait = WebDriverWait(driver, 30)
        
        print("--- 4. كتابة العنوان...")
        title_field = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')
        ))
        title_field.click()
        title_field.send_keys(final_title)
        
        print("--- 5. إدراج المحتوى مع الصور...")
        story_field = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')
        ))
        story_field.click()
        
        js_script = """
        const html = arguments[0];
        const blob = new Blob([html], { type: 'text/html' });
        const item = new ClipboardItem({ 'text/html': blob });
        navigator.clipboard.write([item]);
        """
        driver.execute_script(js_script, full_html_content)
        story_field.send_keys(Keys.CONTROL, 'v')
        
        print("--- ⏳ انتظار رفع الصور...")
        time.sleep(12)
        
        print("--- 6. بدء النشر...")
        publish_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')
        ))
        publish_button.click()
        
        print("--- 7. إضافة الوسوم...")
        if ai_tags:
            try:
                tags_input = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')
                ))
                tags_input.click()
                
                for tag in ai_tags[:5]:
                    tags_input.send_keys(tag)
                    time.sleep(0.5)
                    tags_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                print(f"--- تمت إضافة الوسوم: {', '.join(ai_tags[:5])}")
            except:
                print("--- تخطي الوسوم")
        
        print("--- 8. النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')
        ))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)
        
        print("--- 9. انتظار معالجة النشر...")
        time.sleep(15)
        
        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! 🎉🎉🎉")
        
    except Exception as e:
        print(f"!!! خطأ: {e}")
        driver.save_screenshot("error_screenshot.png")
        with open("error_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
