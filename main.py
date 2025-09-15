import feedparser
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- الإعدادات ---
RSS_URL = "https://fastyummyfood.com/feed" # تم تحديث الرابط بناءً على السجل
POSTED_LINKS_FILE = "posted_links.txt"

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE): return set()
    with open(POSTED_LINKS_FILE, "r", encoding='utf-8') as f: return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a", encoding='utf-8') as f: f.write(link + "\n")

def get_next_post_to_publish():
    print(f"--- 1. البحث عن مقالات في: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("!!! لا توجد مقالات في الـ RSS.")
        return None
    print(f"--- تم العثور على {len(feed.entries)} مقالات.")
    posted_links = get_posted_links()
    for entry in reversed(feed.entries):
        if entry.link not in posted_links:
            print(f">>> تم تحديد المقال: {entry.title}")
            return entry
    return None

def main():
    print("--- بدء تشغيل الروبوت (الإصدار v6 - المحقق) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة لنشرها.")
        return

    cookie_value = os.environ.get("MEDIUM_COOKIE")
    if not cookie_value:
        print("!!! خطأ: لم يتم العثور على كوكي 'MEDIUM_COOKIE'.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920,1080")
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": cookie_value, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        
        # حفظ لقطة شاشة وكود الصفحة للمساعدة في التشخيص
        time.sleep(5) # انتظر 5 ثواني لتحميل الصفحة
        driver.save_screenshot("debug_screenshot_before_title.png")
        with open("debug_page_source_before_title.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        
        wait = WebDriverWait(driver, 20)
        
        print("--- 4. البحث عن حقل العنوان...")
        title_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[aria-label="Title"]')))
        print("--- تم العثور على حقل العنوان.")
        title_field.send_keys(post_to_publish.title)
        
        print("--- 5. البحث عن حقل المحتوى...")
        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-placeholder="Tell your story…"]')))
        print("--- تم العثور على حقل المحتوى.")
        story_field.click()
        time.sleep(1)

        # المحتوى يأتي في 'content' وليس 'summary' في بعض الأحيان
        content_html = ""
        if 'content' in post_to_publish and post_to_publish.content:
            content_html = post_to_publish.content[0].value
        else:
            content_html = post_to_publish.summary
            
        driver.execute_script("document.execCommand('insertHTML', false, arguments[0]);", content_html)
        
        print("--- 6. انتظار الحفظ...")
        time.sleep(10)

        add_posted_link(post_to_publish.link)
        print(">>> النتيجة النهائية: تم حفظ المقال كمسودة بنجاح!")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
