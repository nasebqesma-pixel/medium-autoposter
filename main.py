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

# --- برمجة ahmed si ---

# ---   غيير فقط اسم موقع بدون تغيير feed       ---
RSS_URL = "https://Fastyummyfood.com/feed" # تم التحديث لاستخدام الرابط من سجل الخطأ
POSTED_LINKS_FILE = "posted_links.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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
    """
    يأخذ بيانات المقال الأصلية ويرسلها إلى Gemini API لإنشاء مقال كامل ومحسن.
    """
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY. سيتم استخدام المحتوى الأصلي.")
        return {"title": title, "content": content_html, "tags": [], "alt_texts": []}

    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    
    prompt = f"""
    You are a professional SEO copywriter for Medium.
    Your task is to take an original recipe title and content, and write a full Medium-style article (around 600 words) optimized for SEO, engagement, and backlinks.

    **Original Data:**
    - Original Title: "{title}"
    - Original Content Snippet: "{clean_content[:1500]}"
    - Link to the full recipe: "{original_link}"
    - Available Image URL: "{image_url}"

    **Article Requirements:**

    1.  **Focus Keyword:** Identify the main focus keyword from the original title.

    2.  **Title:** Create a new title using the Hybrid Headline strategy.
        - Start with the focus keyword.
        - Add a curiosity or benefit hook.
        - Keep it under 65 characters.
        - Example: "Pumpkin Cheesecake Truffles Delight: Why Bakers Love This No-Bake Fall Treat."

    3.  **Article Body (HTML Format):**
        - Write a 600-700 word article in clean HTML.
        - **Intro:** Open with the focus keyword. Build curiosity and authority.
        - **Keyword Usage:** Use the focus keyword exactly 4 times. Naturally include related supporting keywords.
        - **Headings:** Use SEO-friendly H2 and H3 headings.
        - **Content Expansion:** Include a mini-listicle (e.g., "3 Creative Ways to Serve This Dessert").
        - **Image Placement:** Insert two image placeholders in the HTML:
            - `<!-- IMAGE 1 PLACEHOLDER -->` after the intro.
            - `<!-- IMAGE 2 PLACEHOLDER -->` before the listicle section.
        - **CTA Placement:** Insert the recipe link `{original_link}` only twice with benefit-driven text.
        - **Reader Engagement:** Include conversational questions.

    4.  **Smart Closing Method (3 short blocks at the end):**
        - A wrap-up sentence.
        - A benefit-driven CTA with the recipe link.
        - A comment invitation asking for feedback or future recipe ideas.

    **Output Format:**
    Return ONLY a valid JSON object with the following keys: "new_title", "new_html_content", "tags", and "alt_texts".

    - `new_html_content`: The full article in HTML format, including the image placeholders.
    - `tags`: An array of exactly 7 relevant Medium tags (each 23 characters or less).
    - `alt_texts`: An array of exactly 2 SEO-optimized Alt Texts for the images. The first should be a lifestyle/presentation description, and the second a close-up detail description.

    **Example JSON Output:**
    {{
      "new_title": "Your Amazing New Title Here",
      "new_html_content": "<h2>Introduction</h2><p>Article intro text...</p><!-- IMAGE 1 PLACEHOLDER --><p>More content...</p><h3>3 Creative Ways...</h3><!-- IMAGE 2 PLACEHOLDER --><p>Conclusion...</p>",
      "tags": ["food", "recipe", "baking", "dessert", "cooking", "easy recipes", "holiday food"],
      "alt_texts": ["A beautiful platter of pumpkin cheesecake truffles ready for a fall party.", "A close-up shot of a single pumpkin cheesecake truffle showing its creamy texture."]
    }}
    """
    
    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 4096,
        }
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
        return {"title": title, "content": content_html, "tags": [], "alt_texts": []}

def main():
    print("--- بدء تشغيل الربوت الناشر v21.1 (نسخة مصححة) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

    original_title = post_to_publish.title
    original_link = post_to_publish.link
    image_url = extract_image_url_from_entry(post_to_publish)
    original_content_html = post_to_publish.summary
    if 'content' in post_to_publish and post_to_publish.content:
        original_content_html = post_to_publish.content[0].value

    rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link, image_url)
    
    final_title = rewritten_data["title"]
    generated_html_content = rewritten_data["content"]
    ai_tags = rewritten_data["tags"]
    ai_alt_texts = rewritten_data["alt_texts"]
    
    full_html_content = generated_html_content
    if image_url:
        alt_text1 = ai_alt_texts[0] if len(ai_alt_texts) > 0 else "Recipe main image"
        alt_text2 = ai_alt_texts[1] if len(ai_alt_texts) > 1 else "Detailed view of the recipe"
        
        # استخدم اسم الموقع من الرابط الأصلي بشكل ديناميكي
        site_name = re.search(r'https?://(?:www\.)?([^/]+)', original_link).group(1) if re.search(r'https?://', original_link) else "our website"
        
        caption1 = f"<em>{alt_text1} - {site_name}</em>"
        caption2 = f"<em>{alt_text2} - {site_name}</em>"
        
        image1_html = f'<figure><img src="{image_url}" alt="{alt_text1}"><figcaption>{caption1}</figcaption></figure>'
        image2_html = f'<figure><img src="{image_url}" alt="{alt_text2}"><figcaption>{caption2}</figcaption></figure>'
        
        full_html_content = full_html_content.replace("<!-- IMAGE 1 PLACEHOLDER -->", image1_html)
        full_html_content = full_html_content.replace("<!-- IMAGE 2 PLACEHOLDER -->", image2_html)

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

        print("--- 4. كتابة العنوان والمحتوى المحسن...")
        title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
        title_field.click()
        title_field.send_keys(final_title)

        story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
        story_field.click()
        
        js_script = "const html = arguments[0]; const blob = new Blob([html], { type: 'text/html' }); const item = new ClipboardItem({ 'text/html': blob }); navigator.clipboard.write([item]);"
        driver.execute_script(js_script, full_html_content)
        story_field.send_keys(Keys.CONTROL, 'v')
        time.sleep(5)

        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم المتاحة...")
        tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
        tags_input.click()
        
        # --- *** الجزء الذي تم تصحيحه *** ---
        final_tags = []
        if ai_tags:
            # الخيار الأول: استخدام الوسوم من Gemini
            final_tags = ai_tags[:5]
        elif hasattr(post_to_publish, 'tags') and post_to_publish.tags:
            # الخيار الثاني (احتياطي): استخدام الوسوم من RSS إذا كانت موجودة
            final_tags = [tag.term for tag in post_to_publish.tags[:5]]
        else:
            # إذا لم يوجد أي شيء، استمر بدون وسوم
            print("--- لم يتم العثور على وسوم من Gemini أو RSS.")
        
        if final_tags:
            for tag in final_tags:
                tags_input.send_keys(tag)
                time.sleep(0.5)
                tags_input.send_keys(Keys.ENTER)
                time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")

        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)

        print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
        time.sleep(15)

        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! 🎉🎉🎉")

    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        driver.save_screenshot("error_screenshot.png")
        with open("error_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        # رفع الخطأ لإيقاف العملية في GitHub Actions
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
