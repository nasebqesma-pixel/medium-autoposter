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

# --- إعدادات عامة ---
RSS_URL = "https://Fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ========== أدوات مساعدة ==========

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE):
        return set()
    with open(POSTED_LINKS_FILE, "r", encoding='utf-8') as f:
        return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a", encoding='utf-8') as f:
        f.write(link + "\n")

def get_next_post_to_publish():
    print(f"--- 1. البحث عن مقالات في: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        return None
    print(f"--- تم العثور على {len(feed.entries)} مقالات.")
    posted_links = get_posted_links()
    for entry in reversed(feed.entries):
        if entry.link not in posted_links:
            print(f">>> تم تحديد المقال: {entry.title}")
            return entry
    return None

def extract_image_url_from_entry(entry):
    # محاولات متعددة لاستخراج رابط الصورة
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media and media.get('medium') == 'image':
                return media['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'href' in enclosure and 'image' in enclosure.get('type', ''):
                return enclosure.href
    content_html = ""
    if 'content' in entry and entry.content:
        content_html = entry.content[0].value
    else:
        content_html = entry.summary
    match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
    if match:
        return match.group(1)
    return None

def rewrite_content_with_gemini(title, content_html, original_link, image_url):
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None

    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    prompt = f"""
You are a professional SEO copywriter for Medium.
Your task is to take an original recipe title and content, and write a full Medium-style article (around 600-700 words) optimized for SEO, engagement, and backlinks.

Original Data:
- Original Title: "{title}"
- Original Content Snippet: "{clean_content[:1500]}"
- Link to the full recipe: "{original_link}"
- Available Image URL: "{image_url}"

Article Requirements:
1) Focus Keyword: Identify it implicitly from the title.
2) Title: Create a compelling Medium-style title.
3) Body: Write a 600-700 word article in clean HTML (no inline styles).
   IMPORTANT: Insert exactly these placeholders as plain HTML comments:
   - <!-- IMAGE 1 PLACEHOLDER --> after the intro paragraph.
   - <!-- IMAGE 2 PLACEHOLDER --> before any list/steps section.
   Do NOT add your own <img> tags.
4) Close with a subtle CTA to visit the source link (do not duplicate the raw link).
Output:
Return ONLY valid JSON with keys: "new_title", "new_html_content", "tags", "alt_texts".
- "tags": up to 5 topical tags
- "alt_texts": two short alt texts for the two images
"""

    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096}
    }
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']

        # في حال رجع محتوى يحتوي على ```json ... ```
        raw_text = re.sub(r'```json|```', '', raw_text).strip()

        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(0)
            result = json.loads(clean_json_str)
            print("--- ✅ تم استلام مقال كامل من Gemini.")
            return {
                "title": result.get("new_title", title),
                "content": result.get("new_html_content", content_html),
                "tags": result.get("tags", []),
                "alt_texts": result.get("alt_texts", [])
            }
        else:
            raise ValueError("لم يتم العثور على صيغة JSON في رد Gemini.")
    except Exception as e:
        print(f"!!! حدث خطأ فادح أثناء التواصل مع Gemini: {e}")
        return None

def build_medium_ready_html(generated_html_content, image_url, alt_texts, original_link):
    """
    الهدف: استبدال الـ placeholders بصور بوسم <img> بسيط فقط (بدون figure/figcaption)
    لأن Medium يُعيد رفع الصور عند لصق <img> بسيط غالباً.
    """
    html = generated_html_content or ""
    site_name = "our website"
    m = re.search(r'https?://(?:www\.)?([^/]+)', original_link or "")
    if m:
        site_name = m.group(1)

    # تجهيز نصوص البدائل
    alt1 = (alt_texts[0] if len(alt_texts) > 0 else "Recipe main image").strip()
    alt2 = (alt_texts[1] if len(alt_texts) > 1 else "Detailed view of the recipe").strip()

    # نبني كتل الصور البسيطة
    # (لا نستخدم <figure>) فقط img + سطر كابتشن منفصل
    def img_block(url, alt):
        caption = f"<p><em>{alt} - {site_name}</em></p>"
        return f'<p><img src="{url}" alt="{alt}"></p>{caption}'

    if image_url:
        img1_html = img_block(image_url, alt1)
        img2_html = img_block(image_url, alt2)

        # استبدال الـ placeholders إن وُجدت
        if "<!-- IMAGE 1 PLACEHOLDER -->" in html:
            html = html.replace("<!-- IMAGE 1 PLACEHOLDER -->", img1_html)
        if "<!-- IMAGE 2 PLACEHOLDER -->" in html:
            html = html.replace("<!-- IMAGE 2 PLACEHOLDER -->", img2_html)

        # في حال لم تُستخدم الـ placeholders (احتياط)
        if ("<!-- IMAGE 1 PLACEHOLDER -->" not in generated_html_content) and ("<!-- IMAGE 2 PLACEHOLDER -->" not in generated_html_content):
            # نضيف صورة في البداية
            html = img1_html + html

    # نضيف CTA لطيف + رابط المصدر في النهاية
    call_to_action = "For the full recipe, step-by-step photos, and detailed tips, visit us at"
    link_html = f'<br><p><em>{call_to_action} <a href="{original_link}" rel="noopener" target="_blank">{site_name}</a>.</em></p>'
    html = html + link_html
    return html

def paste_html_into_editor(driver, element, html):
    """
    نحاول اللصق بطريقة clipboard 'text/html'، ثم نضغط Ctrl+V.
    في حال فشل clipboard على بعض البيئات، نحاول fallback باستخدام insertHTML.
    """
    paste_js = r"""
    const html = arguments[0];
    try {
      const blob = new Blob([html], { type: 'text/html' });
      const item = new ClipboardItem({ 'text/html': blob });
      await navigator.clipboard.write([item]);
      return "clipboard_ok";
    } catch (e) {
      try {
        document.execCommand('insertHTML', false, html);
        return "exec_insertHTML_ok";
      } catch (e2) {
        return "failed";
      }
    }
    """
    # جرّب الكتابة للـ clipboard (قد تعمل) ثم Ctrl+V
    try:
        result = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            (async () => {
              const res = await (new Function(`return (async ()=>{ %s })()`))();
              done(res);
            })().catch(e => done("failed"));
        """ % paste_js.replace("\n", "\n"), html)
    except Exception:
        result = "failed"

    if result == "clipboard_ok":
        element.send_keys(Keys.CONTROL, 'v')
    elif result == "exec_insertHTML_ok":
        pass
    else:
        # محاولة أخيرة مباشرة بـ insertHTML دون Async
        try:
            driver.execute_script("document.execCommand('insertHTML', false, arguments[0]);", html)
        except Exception:
            # fallback أخير: الصق كنص (لن يُدخل صور) — فقط كمل وما نعتمد عليه.
            element.send_keys(html)

# ========== التنفيذ الرئيسي ==========

def main():
    print("--- بدء تشغيل الروبوت الناشر v22 (تصحيح لصق الصور) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

    original_title = post_to_publish.title
    original_link = post_to_publish.link

    # اكتشاف صورة المقال من RSS
    image_url = extract_image_url_from_entry(post_to_publish)
    if image_url:
        print(f"--- 🖼️ تم العثور على رابط الصورة: {image_url}")
    else:
        print("--- ⚠️ لم يتم العثور على رابط صورة في RSS لهذا المقال.")

    # جلب المحتوى الأصلي
    original_content_html = ""
    if 'content' in post_to_publish and post_to_publish.content:
        original_content_html = post_to_publish.content[0].value
    else:
        original_content_html = post_to_publish.summary

    # توليد المحتوى عبر Gemini
    rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link, image_url)

    if rewritten_data:
        final_title = rewritten_data["title"]
        generated_html_content = rewritten_data["content"]
        ai_tags = rewritten_data.get("tags", [])
        ai_alt_texts = rewritten_data.get("alt_texts", [])
        # نبني HTML مناسب للّصق في Medium (img بسيط)
        full_html_content = build_medium_ready_html(generated_html_content, image_url, ai_alt_texts, original_link)
    else:
        print("--- سيتم استخدام المحتوى الأصلي بسبب فشل Gemini.")
        final_title = original_title
        ai_tags = []
        # نفس أسلوب الكود الأول: img بسيط + المحتوى الأصلي + CTA
        image_html = f'<p><img src="{image_url}" alt="Recipe image"></p>' if image_url else ""
        site_name = "our website"
        m = re.search(r'https?://(?:www\.)?([^/]+)', original_link or "")
        if m:
            site_name = m.group(1)
        call_to_action = "For the full recipe, step-by-step photos, and detailed tips, visit us at"
        link_html = f'<br><p><em>{call_to_action} <a href="{original_link}" rel="noopener" target="_blank">{site_name}</a>.</em></p>'
        full_html_content = image_html + original_content_html + link_html

    # --- Selenium للنشر على Medium ---
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
    # خيارات إضافية اختيارية للاستقرار
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True
    )

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
        title_field.send_keys(final_title)

        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
        story_field.click()

        # لصق HTML في المحرر (img بسيط يجب أن يجبر Medium على إعادة رفع الصورة)
        paste_html_into_editor(driver, story_field, full_html_content)
        time.sleep(6)  # إتاحة وقت للمحرّر لمعالجة الصور

        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم...")
        # خذ من Gemini، وإن لم تتوفر، جرّب من RSS
        final_tags = [t for t in (ai_tags or []) if t][:5]
        if not final_tags and hasattr(post_to_publish, 'tags'):
            final_tags = [tag.term for tag in post_to_publish.tags[:5]]

        if final_tags:
            tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
            tags_input.click()
            for tag in final_tags:
                tags_input.send_keys(tag)
                time.sleep(0.4)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(0.8)
            print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")
        else:
            print("--- لا توجد وسوم لإضافتها.")

        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)

        print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
        time.sleep(15)

        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! والصور ينبغي أن تكون مرفوعة على سيرفر Medium 🎉🎉🎉")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        try:
            driver.save_screenshot("error_screenshot.png")
            with open("error_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
