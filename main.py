import feedparser
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
import re

RSS_URL = "https://fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"

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

def main():
    print("--- بدء تشغيل الروبوت الكامل v12.1 (إصلاح برمجي) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

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
        
        print("--- 4. كتابة العنوان...")
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
        title_field.click()
        title_field.send_keys(post_to_publish.title)
        print("--- تم كتابة العنوان بنجاح!")
        
        print("--- 5. بناء المحتوى الكامل...")
        image_url = extract_image_url_from_entry(post_to_publish)
        image_html = f'<img src="{image_url}"><br>' if image_url else ""
        
        text_content_html = ""
        if 'content' in post_to_publish and post_to_publish.content:
            text_content_html = post_to_publish.content[0].value
        else:
            text_content_html = post_to_publish.summary

        original_link = post_to_publish.link
        link_html = f'<br><p><em>Originally published at <a href="{original_link}" rel="noopener" target="_blank">Fastyummyfood.com</a>.</em></p>'

        full_html_content = image_html + text_content_html + link_html

        print("--- 6. محاكاة عملية النسخ واللصق...")
        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
        story_field.click()

        # --- هنا الإصلاح ---
        # قمنا بوضع النص متعدد الأسطر في متغير أولاً
        js_script = """
            const html = arguments[0];
            const blob = new Blob([html], { type: 'text/html' });
            const item = new ClipboardItem({ 'text/html': blob });
            navigator.clipboard.write([item]);
        """
        driver.execute_script(js_script, full_html_content)
        # --- نهاية الإصلاح ---
        
        print("--- تم وضع المحتوى الكامل في الحافظة.")

        story_field.send_keys(Keys.CONTROL, 'v')
        print("--- تم لصق المحتوى الكامل بنجاح!")

        print("--- 7. انتظار الحفظ...")
        time.sleep(15)

        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 النجاح النهائي! تم حفظ المقال الكامل كمسودة! 🎉🎉🎉")

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
