import os
import re
import random
import time
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
from google.generativeai.types import RequestOptions
from io import BytesIO
from urllib.parse import quote

# Настройка Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-3.5-flash-lite")

# Список источников
FEEDS = [
    "https://variety.com/feed/",
    "https://www.hollywoodreporter.com/feed/",
    "https://www.rollingstone.com/music/music-news/feed/",
    "https://www.rollingstone.com/culture/feed/",
    "https://www.billboard.com/feed/",
    "https://deadline.com/feed/",
    "https://www.thewrap.com/feed/",
    "https://netinfluencer.com/feed/",
    "https://creatoriq.com/blog/rss.xml",
    "https://www.adweek.com/category/influencer-marketing/feed/",
    "https://lenta.ru/rss/news",
    "https://www.gazeta.ru/export/rss/first.xml",
    "https://aif.ru/rss/culture.php",
    "https://kulturomania.ru/feed/",
    "https://dzen.ru/bloggg/rss",
    "https://dzen.ru/russianteleweek.ru",
    "https://www.comingsoon.net/feed",
    "https://feeds.skynews.com/feeds/rss/entertainment.xml",
    "https://variety.com/v/film/feed/",
    "https://www.hollywoodreporter.com/c/movies/feed/"
]

CULTURE_KEYWORDS = ["кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер", "блогер", "тиктокер", "инфлюенсер", "стример", "контент", "звезд", "артист", "шоу", "фестиваль", "концерт"]
BAD_WORDS = ["ukraine", "war", "politics", "military", "election", "poll", "voter", "president", "government", "украин", "войн", "политик", "спецоперац", "выборы", "явка", "избирател", "президент", "правительств", "госдума"]

def get_news_from_feed(feed_url):
    news_list = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(feed_url, timeout=15, headers=headers)
        root = ET.fromstring(response.content)
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            desc = item.find("description").text or ""
            link = item.find("link").text or ""
            if any(bad in (title + desc).lower() for bad in BAD_WORDS): continue
            if any(domain in feed_url for domain in ["lenta", "gazeta", "aif", "kulturomania", "dzen"]):
                if not any(kw in (title + desc).lower() for kw in CULTURE_KEYWORDS): continue
            news_list.append({"title": title, "link": link, "description": desc})
    except Exception as e:
        pass
    return news_list

def generate_post_text(title, link, description):
    prompt = (
        "Ты — редактор канала 'MEDIA'. Твой стиль: дерзко, коротко, без воды. "
        "Перепиши эту новость на русский язык. Сделай это ОЧЕНЬ КОРОТКО: максимум 3-4 предложения. "
        "Добавь эмодзи (3-5 штук).\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат (СТРОГО): Заголовок с эмодзи. Пустая строка. Текст. Пустая строка. '🔗 [Источник](URL)'. Хэштеги (3-4).\n\n"
        "ВАЖНО: В самом конце добавь скрытую строку [IMG: тег1, тег2]. "
        "НЕ пиши имена знаменитостей! Опиши ВИЗУАЛЬНУЮ СЦЕНУ для генерации обложки (например: neon microphone in smoke, dark courtroom gavel, cinematic red carpet lights, abstract movie film reel)."
    )
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
            full_text = response.text
            full_text = re.sub(r"^\d+\.\s*", "", full_text.strip())
            
            img_match = re.search(r"\[IMG:\s*(.*?)\]", full_text, re.IGNORECASE)
            search_query = "dark cinematic abstract background"
            if img_match:
                search_query = img_match.group(1).strip()
                full_text = full_text.replace(img_match.group(0), "").strip()
            return full_text, search_query
        except Exception as e:
            time.sleep(3)
    return None, None

def generate_image(query):
    print(f"Генерируем обложку по запросу: {query}")
    # Усилитель стиля: темный, дорогой, кинематографичный
    style_boost = ", dark moody cinematic lighting, neon accents, highly detailed, 8k resolution, photorealistic, dramatic shadows, masterpiece"
    full_prompt = query + style_boost
    
    try:
        encoded_prompt = quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true&model=flux&seed={random.randint(1, 999999)}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return BytesIO(response.content)
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return None

def send_to_telegram(text, image_bytes=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    
    try:
        if image_bytes:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            files = {'photo': ('image.jpg', image_bytes, 'image/jpeg')}
            data = {'chat_id': channel_id, 'caption': text, 'parse_mode': 'HTML'}
            resp = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": channel_id, "text": text, "parse_mode": "HTML"}
            resp = requests.post(url, json=payload, timeout=30)
        
        if resp.status_code == 200:
            print("Пост опубликован!")
        else:
            print(f"Ошибка Telegram: {resp.text}")
    except Exception as e:
        print(f"Сбой отправки: {e}")

if __name__ == "__main__":
    random.shuffle(FEEDS)
    all_news = []
    seen_titles = set()
    
    for feed in FEEDS:
        news_items = get_news_from_feed(feed)
        for news in news_items[:3]:
            if news['title'] not in seen_titles:
                seen_titles.add(news['title'])
                all_news.append(news)
    
    print(f"Найдено новостей: {len(all_news)}")
    
    for index, news in enumerate(all_news):
        post_text, img_query = generate_post_text(news['title'], news['link'], news['description'])
        if post_text:
            img = generate_image(img_query)
            send_to_telegram(post_text, img)
            if index < len(all_news) - 1:
                print("Ждем 30 секунд...")
                time.sleep(30)
