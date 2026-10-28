import os
import re
import random
import time
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
from google.generativeai.types import RequestOptions
from io import BytesIO

# Настройка Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-3.5-flash-lite")

# --- РАСШИРЕННЫЙ СПИСОК ИСТОЧНИКОВ ---
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

# Ключевые слова для российских СМИ
CULTURE_KEYWORDS = [
    "кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер",
    "блогер", "тиктокер", "инфлюенсер", "стример", "тикток", "ютуб", "инстаграм", "контент", "ролик",
    "звезд", "артист", "шоу", "теле", "фестиваль", "концерт"
]

# ЖЕСТКИЙ ФИЛЬТР ПОЛИТИКИ
BAD_WORDS = [
    "ukraine", "war", "politics", "military", "conflict", "election", "poll", "voter", "president", "government", "parliament",
    "украин", "войн", "политик", "спецоперац", "выборы", "явка", "избирател", "парламент", "президент", "правительств", "госдума"
]

def get_news_from_feed(feed_url):
    news_list = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(feed_url, timeout=15, headers=headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            link = item.find("link").text or ""
            description = item.find("description").text or ""
            
            if any(bad in (title + description).lower() for bad in BAD_WORDS):
                continue
            
            if any(domain in feed_url for domain in ["lenta", "gazeta", "aif", "kulturomania", "dzen"]):
                if not any(kw in (title + description).lower() for kw in CULTURE_KEYWORDS):
                    continue
            
            news_list.append({"title": title, "link": link, "description": description})
            
    except Exception as e:
        pass
    return news_list

def generate_post_text(title, link, description):
    # УСИЛЕННЫЙ ПРОМТ: делаем акцент на "интересности" и точных тегах для картинки
    prompt = (
        "Ты — крутой журналист-колумнист канала 'MEDIA'. Твой стиль: индустрия без прикрас, живой язык, легкая ирония, без сухих пресс-релизов. "
        "Твоя задача — написать пост, который захочется дочитать до конца. "
        "Перепиши эту новость на русский язык так, чтобы она звучала как увлекательная история. "
        "Добавь много эмодзи (4-6 штук), чтобы текст был ярким. "
        "В конце добавь ссылку на источник и 3-4 релевантных хэштега (например #кино #премьера #MEDIA).\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат ответа:\n"
        "1. Цепляющий заголовок с эмодзи.\n"
        "2. Интересный текст (2-3 абзаца) с эмодзи.\n"
        "3. Ссылка: '🔗 [Источник](URL)'\n"
        "4. Хэштеги.\n\n"
        "ВАЖНО: В самом конце, после хэштегов, добавь скрытую строку [IMG: тег1, тег2, тег3] — "
        "3-5 конкретных английских слов, которые идеально описывают визуальный образ этой новости (например: cinema, red carpet, concert, celebrity, movie premiere)."
    )
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
            full_text = response.text
            
            # Извлекаем теги для картинки
            img_match = re.search(r"\[IMG:\s*(.*?)\]", full_text, re.IGNORECASE)
            search_query = "entertainment"
            if img_match:
                search_query = img_match.group(1).strip()
                full_text = full_text.replace(img_match.group(0), "").strip()
            
            return full_text, search_query
        except Exception as e:
            print(f"Ошибка Gemini (попытка {attempt+1}): {e}")
            time.sleep(3)
    return None, None

def get_image(query):
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        print("ОШИБКА: Не найден PIXABAY_API_KEY!")
        return None

    url = "https://pixabay.com/api/"
    # Увеличиваем выборку до 20 картинок, чтобы найти максимально подходящую
    params = {
        "key": api_key, 
        "q": query, 
        "image_type": "photo", 
        "orientation": "horizontal", 
        "safesearch": "true", 
        "per_page": 20 
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get("hits"):
            # Берем случайную из 20 найденных, чтобы картинки не повторялись
            photo_url = random.choice(data["hits"])["largeImageURL"]
            img_data = requests.get(photo_url, timeout=15).content
            return BytesIO(img_data)
        else:
            print(f"Pixabay не нашел фото по запросу: '{query}'")
            return None
    except Exception as e:
        print(f"Ошибка Pixabay: {e}")
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
            return True
        else:
            print(f"Ошибка Telegram: {resp.text}")
            return False
    except Exception as e:
        print(f"Сбой отправки: {e}")
        return False

if __name__ == "__main__":
    random.shuffle(FEEDS)
    all_news = []
    
    for feed in FEEDS:
        news_items = get_news_from_feed(feed)
        all_news.extend(news_items[:3]) 
    
    print(f"Найдено новостей: {len(all_news)}")
    
    for index, news in enumerate(all_news):
        post_text, search_query = generate_post_text(news['title'], news['link'], news['description'])
        if post_text:
            img = get_image(search_query)
            send_to_telegram(post_text, img)
            
            if index < len(all_news) - 1:
                print("Ждем 30 секунд...")
                time.sleep(30)
