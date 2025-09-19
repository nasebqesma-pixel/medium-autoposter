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
from bs4 import BeautifulSoup

# --- medium المكتبة الجديدة لمحاكاة الإنسان في النشر على ---
# --- برمجة ahmed si ---

RSS_URL = "https://Fastyummyfood.com/feed" # تم التحديث حسب سجلات الخطأ
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

# --- [التحسين] دالة جديدة وأكثر قوة لاستخلاص المقدمة ---
def extract_intro_from_html(html_content, num_elements=3):
    """
    تستخلص هذه الدالة عددًا معينًا من العناصر (فقرات أو حاويات نصية)
    لتكون أكثر مرونة مع مختلف تنسيقات RSS.
    """
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # ابحث عن الفقرات أو الحاويات النصية الرئيسية (p أو div)
    # هذا يجعلها أكثر قوة إذا كان المحتوى غير منظم في فقرات <p>
    elements = soup.find_all(['p', 'div'])
    
    intro_html = ""
    count = 0
    
    for el in elements:
        # تجاهل العناصر الفارغة أو التي لا تحتوي على نص مباشر
        if el.get_text(strip=True):
            # تجاهل الحاويات الكبيرة التي تحتوي على عناصر أخرى قمنا بمعالجتها بالفعل
            if el.find(['p', 'div']):
                continue
            intro_html += str(el)
            count += 1
            if count >= num_elements:
                break
                
    # خطة بديلة: إذا لم يتم العثور على أي عناصر، ارجع للملخص الأصلي
    # وقم بتنظيفه من أي وسوم HTML متبقية
    if not intro_html:
        # استخدم الملخص المتاح ولكن نظفه
        soup_fallback = BeautifulSoup(html_content, 'html.parser')
        return soup_fallback.get_text(separator='\n\n', strip=True)

    return intro_html


def main():
    print("--- بدء تشغيل الروبوت الناشر v19 (النسخة الذهبية) ---")
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
        
        print("--- 4. كتابة العنوان والمحتوى...")
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
        title_field.click()
        title_field.send_keys(post_to_publish.title)
        
        image_url = extract_image_url_from_entry(post_to_publish)
        image_html = f'<img src="{image_url}">' if image_url else ""
        
        raw_content_html = ""
        if 'content' in post_to_publish and post_to_publish.content:
            raw_content_html = post_to_publish.content[0].value
        else:
            raw_content_html = post_to_publish.summary

        # استدعاء الدالة المحسّنة للحصول على المقدمة (مثلاً، أول 3 عناصر نصية)
        intro_content = extract_intro_from_html(raw_content_html, num_elements=3)
        
        # --- [التشخيص] طباعة المحتوى قبل وبعد المعالجة ---
        print("="*50)
        print("--- [تشخيص] محتوى RSS الخام المستلم ---")
        print(raw_content_html)
        print("--- [تشخيص] المحتوى بعد المعالجة (المقدمة) ---")
        print(intro_content)
        print("="*50)

        original_link = post_to_publish.link
        call_to_action = "Love this sneak peek? 🌟 **Continue reading the full recipe, including step-by-step photos and tips, on our main blog.**"
        link_html = f'<br><p><em>{call_to_action} <a href="{original_link}" rel="noopener" target="_blank">Click here to visit Fastyummyfood.com</a>.</em></p>'
        
        full_html_content = image_html + intro_content + link_html

        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
        story_field.click()
        
        js_script = "const html = arguments[0]; const blob = new Blob([html], { type: 'text/html' }); const item = new ClipboardItem({ 'text/html': blob }); navigator.clipboard.write([item]);"
        driver.execute_script(js_script, full_html_content)
        story_field.send_keys(Keys.CONTROL, 'v')
        time.sleep(5)

        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم...")
        tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
        tags_input.click()
        
        if hasattr(post_to_publish, 'tags'):
            tags_to_add = [tag.term for tag in post_to_publish.tags[:5]]
            for tag in tags_to_add:
                tags_input.send_keys(tag)
                time.sleep(0.5)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(tags_to_add)}")

        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)
        
        print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
        time.sleep(15)
        
        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم إرسال أمر النشر بنجاح! 🎉🎉🎉")

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
