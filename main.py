import feedparser
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from html import unescape

# --- الإعدادات ---
RSS_URL = "https://fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE): return set()
    with open(POSTED_LINKS_FILE, "r", encoding='utf-8') as f: return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a", encoding='utf-8') as f: f.write(link + "\n")

def get_next_post_to_publish():
    print(f"--- البحث عن مقالات جديدة في: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("!!! تحذير: الـ RSS فارغ أو لا يمكن الوصول إليه.")
        return None
    print(f"--- تم العثور на {len(feed.entries)} مقال في الـ RSS.")
    posted_links = get_posted_links()
    for entry in reversed(feed.entries):
        if entry.link not in posted_links:
            print(f">>> تم تحديد المقال التالي للنشر: {entry.title}")
            return entry
    return None

def clean_html(raw_html):
    decoded_html = unescape(raw_html)
    cleanr = re.compile('<(script|style|iframe|form).*?>.*?</(script|style|iframe|form)>', re.DOTALL)
    clean_text = re.sub(cleanr, '', decoded_html)
    return clean_text

def main():
    print("--- بدء تشغيل روبوت النشر (الإصدار النهائي v5 - الصبور) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة. المهمة انتهت بنجاح.")
        return

    cookie_value = os.environ.get("MEDIUM_COOKIE")
    if not cookie_value:
        print("!!! خطأ: لم يتم العثور على كوكي الجلسة 'MEDIUM_COOKIE'.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920,1080")
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        print("1. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "uid", "value": cookie_value, "domain": ".medium.com"})
        driver.add_cookie({"name": "sid", "value": cookie_value, "domain": ".medium.com"})
        
        print("2. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        
        wait = WebDriverWait(driver, 45) # **زيادة مدة الانتظار القصوى إلى 45 ثانية**

        print("3. كتابة العنوان...")
        title_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[aria-label="Title"]')))
        title_field.send_keys(post_to_publish.title)
        
        # --- الجزء المحسّن والأكثر أهمية ---
        print("4. انتظار تحميل حقل المحتوى بشكل كامل...")
        # سننتظر حتى يظهر العنصر ويصبح قابلاً للنقر عليه
        story_field_placeholder = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'p[data-placeholder="Tell your story…"]')
            )
        )
        
        print("5. كتابة المحتوى...")
        # استخدام النقر عبر JavaScript لضمان التفعيل
        driver.execute_script("arguments[0].click();", story_field_placeholder)
        time.sleep(1) # إعطاء فرصة للمعالج للاستجابة

        content_html = clean_html(post_to_publish.summary)
        # لصق المحتوى بطريقة آمنة
        driver.execute_script("document.execCommand('insertHTML', false, arguments[0]);", content_html)
        
        print("6. انتظار الحفظ التلقائي...")
        time.sleep(15) # **زيادة مدة انتظار الحفظ**

        print("7. التحقق من نجاح العملية...")
        sample_text = post_to_publish.title[:50]
        if sample_text in driver.page_source:
            print(">>> النجاح مؤكد! تم العثور على المحتوى في الصفحة.")
            add_posted_link(post_to_publish.link)
            print(">>> النتيجة النهائية: تم حفظ المقال كمسودة بنجاح!")
        else:
            print("!!! فشل التحقق! لم يتم العثور على المحتوى في الصفحة بعد الكتابة.")
            driver.save_screenshot("verification_failed.png") # لقطة شاشة للتحقق
            raise Exception("Verification failed: Content not found on page after paste.")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        driver.save_screenshot("error_screenshot.png")
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
