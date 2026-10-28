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

# Список источников
FEEDS = [
    "https://variety.com/feed/",
    "https://www.hollywoodreporter.com/feed/",
    "https://www.rollingstone.com/music/music-news/feed/",
    "https://lenta.ru/rss/news",
    "https://www.gazeta.ru/export/rss/first.xml"
]

# Ключевые слова для российских СМИ
CULTURE_KEYWORDS = [
    "кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер",
    "блогер", "тиктокер", "инфлюенсер", "стример", "тикток", "ютуб", "инстаграм", "контент", "ролик"
]

# ЖЕСТКИЙ ФИЛЬТР ПОЛИТИКИ
BAD_WORDS = [
    "ukraine", "war", "politics", "military", "conflict", "election", "poll", "voter", "president", "government", "parliament",
    "украин", "войн", "политик", "спецоперац", "выборы", "явка", "избирател", "парламент", "президент", "правительств", "госдума"
]

def get_news_from_feed(feed_url):
    """Берет ВСЕ подходящие новости из одной ленты."""
    news_list = []
    try:
        print(f"Проверяем: {feed_url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(feed_url, timeout=15, headers=headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            link = item.find("link").text or ""
            description = item.find("description").text or ""
            
            # Фильтр политики
            if any(bad in (title + description).lower() for bad in BAD_WORDS):
                continue
            
            # Фильтр для российских СМИ
            if "lenta" in feed_url or "gazeta" in feed_url:
                if not any(kw in (title + description).lower() for kw in CULTURE_KEYWORDS):
                    continue
            
            news_list.append({"title": title, "link": link, "description": description})
            
    except Exception as e:
        print(f"Ошибка {feed_url}: {e}")
    return news_list

def generate_post_text(title, link, description):
    prompt = (
        "Ты — редактор канала 'MEDIA'. Твой стиль: индустрия без прикрас, без воды. "
        "Перепиши эту новость на русский язык в 2-3 предложениях. "
        "Добавь эмодзи и легкую иронию. В конце добавь ссылку на источник и 3-4 релевантных хэштега (например #кино #премьера #MEDIA).\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат: Заголовок с эмодзи, текст, ссылка '🔗 [Источник](URL)', хэштеги.\n"
        "ВАЖНО: В самом конце добавь скрытую строку [IMG: слово1, слово2] для поиска картинки."
    )
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
            full_text = response.text
            
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
        return None

    url = "https://pixabay.com/api/"
    params = {"key": api_key, "q": query, "image_type": "photo", "orientation": "horizontal", "safesearch": "true", "per_page": 5}
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        if data.get("hits"):
            photo_url = random.choice(data["hits"])["largeImageURL"]
            img_data = requests.get(photo_url, timeout=15).content
            return BytesIO(img_data)
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
    
    # Собираем новости со всех лент (берем до 5 новостей с каждого источника)
    for feed in FEEDS:
        news_items = get_news_from_feed(feed)
        all_news.extend(news_items[:5]) 
    
    print(f"Найдено новостей для публикации: {len(all_news)}")
    
    # Публикуем по очереди
    for index, news in enumerate(all_news):
        post_text, search_query = generate_post_text(news['title'], news['link'], news['description'])
        if post_text:
            img = get_image(search_query)
            send_to_telegram(post_text, img)
            
            # Если это не последняя новость в списке, делаем паузу 30 секунд
            if index < len(all_news) - 1:
                print("Ждем 30 секунд перед следующим постом...")
                time.sleep(30)
