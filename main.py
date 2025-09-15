import feedparser
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- الإعدادات ---
RSS_URL = "https://fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE):
        return set()
    with open(POSTED_LINKS_FILE, "r") as f:
        return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a") as f:
        f.write(link + "\n")

def get_latest_post():
    feed = feedparser.parse(RSS_URL)
    posted_links = get_posted_links()
    for entry in feed.entries:
        if entry.link not in posted_links:
            return entry
    return None

def main():
    print("--- بدء تشغيل روبوت النشر على Medium (باستخدام كوكي الجلسة) ---")
    
    latest_post = get_latest_post()
    if not latest_post:
        print("لا توجد مقالات جديدة لنشرها.")
        return

    print(f"تم العثور على مقال جديد: {latest_post.title}")

    session_cookie = os.environ.get("MEDIUM_SESSION_COOKIE")
    if not session_cookie:
        print("خطأ: لم يتم العثور على كوكي الجلسة في خزنة GitHub.")
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # 1. حقن الكوكي لتجاوز تسجيل الدخول
        # نذهب إلى الموقع أولاً لتهيئة سياق النطاق
        print("جاري تهيئة الجلسة...")
        driver.get("https://medium.com/")
        
        # نضيف الكوكي الخاص بنا
        driver.add_cookie({
            'name': 'sid',
            'value': session_cookie,
            'domain': '.medium.com'
        })
        print("تم حقن كوكي الجلسة بنجاح.")

        # 2. إنشاء مقال جديد مباشرة
        print("جاري إنشاء مقال جديد...")
        driver.get("https://medium.com/new-story")
        
        wait = WebDriverWait(driver, 20)
        
        # إدخال العنوان
        title_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[aria-label="Title"]')))
        title_field.send_keys(latest_post.title)
        
        # إدخال المحتوى
        content_html = ""
        if 'summary' in latest_post:
            content_html = latest_post.summary
        elif 'content' in latest_post:
            # أحيانًا يكون المحتوى في حقل مختلف
            content_html = latest_post.content[0].value

        content_field = driver.find_element(By.CSS_SELECTOR, 'div.section-inner.layoutSingleColumn')
        driver.execute_script("arguments[0].innerHTML = arguments[1];", content_field, content_html)
        
        print("تمت كتابة المقال.")
        time.sleep(5) 

        print("تم حفظ المقال كمسودة في حسابك على Medium بنجاح!")
        
        add_posted_link(latest_post.link)

    except Exception as e:
        print(f"حدث خطأ: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
