import feedparser
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# --- المكتبة الجديدة: الروبوت الشبح ---
from selenium_stealth import stealth

# --- الإعدادات ---
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
    print("--- بدء تشغيل الروبوت الشبح (الإصدار v7) ---")
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
    options.add_argument("start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # --- تفعيل وضع الشبح ---
    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )
    # --- انتهى التفعيل ---
    
    try:
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": cookie_value, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        
        wait = WebDriverWait(driver, 30)
        
        print("--- 4. البحث عن حقل العنوان...")
        title_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[aria-label="Title"]')))
        title_field.send_keys(post_to_publish.title)
        
        print("--- 5. البحث عن حقل المحتوى...")
        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-placeholder="Tell your story…"]')))
        story_field.click()
        time.sleep(1)

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
        driver.save_screenshot("error_screenshot.png")
        with open("error_page_source.html", "w", encoding="utf-8") as f: f.write(driver.page_source)
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
