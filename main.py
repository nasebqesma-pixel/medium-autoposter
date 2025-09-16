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
# --- المكتبة الجديدة لمحاكاة الإنسان ---
from selenium.webdriver.common.action_chains import ActionChains

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

def main():
    print("--- بدء تشغيل الروبوت الناشر v18 (النقر البشري) ---")
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
    # ... (باقي الخيارات) ...
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    
    try:
        # ... (الخطوات من 2 إلى 6 تبقى كما هي) ...
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": sid_cookie, "domain": ".medium.com"})
        driver.add_cookie({"name": "uid", "value": uid_cookie, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        
        wait = WebDriverWait(driver, 30)
        
        print("--- 4. كتابة العنوان والمحتوى...")
        # ... (كود كتابة العنوان والمحتوى كما هو) ...
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
        title_field.click()
        title_field.send_keys(post_to_publish.title)
        
        # ... (كود بناء ولصق المحتوى كما هو) ...
        
        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم...")
        # ... (كود إضافة الوسوم كما هو) ...

        # --- هنا يبدأ الإصلاح الحاسم ---
        print("--- 7. محاكاة النقر البشري على زر النشر النهائي...")
        
        # 1. ننتظر حتى يكون الزر موجودًا ومستقرًا
        publish_now_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2) # انتظار إضافي للاستقرار

        # 2. إنشاء سلسلة من الإجراءات البشرية
        actions = ActionChains(driver)
        actions.move_to_element(publish_now_button) # حرك الماوس إلى الزر
        actions.click(publish_now_button)           # انقر
        actions.perform()                           # نفذ الإجراءات
        
        print("--- تم إرسال أمر النقر البشري.")

        print("--- 8. انتظار نهائي للتأكد من النشر...")
        time.sleep(15)
        
        # 9. التقاط الأدلة
        driver.save_screenshot("final_result_screenshot.png")
        with open("final_result_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("--- تم التقاط صورة وحفظ المصدر بعد النقر النهائي.")

        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم إرسال أمر النشر، يرجى التحقق من النتيجة. 🎉🎉🎉")

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
