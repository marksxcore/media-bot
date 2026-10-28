import os
import re
import json
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

# --- ПОЛНЫЙ СПИСОК ИСТОЧНИКОВ (18 ШТУК) ---
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
    "https://feeds.skynews.com/feeds/rss/entertainment.xml"
]

CULTURE_KEYWORDS = ["кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер", "блогер", "тиктокер", "инфлюенсер", "стример", "контент", "звезд", "артист", "шоу", "фестиваль", "концерт"]

BAD_WORDS = [
    "ukraine", "war", "politics", "military", "election", "poll", "voter", "president", "government", "parliament",
    "украин", "войн", "политик", "спецоперац", "выборы", "явка", "избирател", "парламент", "президент", "правительств", "госдума",
    "сербия", "белград", "премьер-министр", "кандидат", "оппозици",
    "рак", "онкологи", "опухол", "химиотерап"
]

HISTORY_FILE = "history.json"
MAX_HISTORY = 500

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)

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
            
            image_url = None
            enclosure = item.find("enclosure")
            if enclosure is not None:
                image_url = enclosure.get("url")
            if not image_url:
                media = item.find("{http://search.yahoo.com/mrss/}content")
                if media is not None:
                    image_url = media.get("url")

            news_list.append({
                "title": title, 
                "link": link, 
                "description": desc,
                "image_url": image_url
            })
    except Exception:
        pass
    return news_list

def is_duplicate(title, history):
    """Проверяет, является ли новость дублем (с учетом истории)."""
    # 1. Быстрая проверка по точному совпадению
    if title in history:
        return True
    
    # 2. Умная проверка через Gemini (последние 5 новостей)
    if not history:
        return False
        
    recent = history[-5:]
    check_prompt = (
        f"Я собираюсь опубликовать новость с заголовком: '{title}'.\n"
        f"Вот список недавно опубликованных заголовков: {recent}.\n"
        "Это та же самая новость (просто другими словами) или абсолютно разное событие? "
        "Ответь строго одним словом: ДА (если это дубль) или НЕТ (если это новое событие)."
    )
    
    try:
        response = model.generate_content(check_prompt, request_options=RequestOptions(timeout=10.0))
        answer = response.text.strip().upper()
        return "ДА" in answer
    except Exception:
        return False

def generate_post_text(title, link, description):
    is_sad_news = any(word in (title + description).lower() for word in ["умер", "смерть", "погиб", "dead", "death", "passed away"])
    
    if is_sad_news:
        tone_instruction = (
            "ВАЖНО: Эта новость о смерти/трагедии. Пиши с уважением, без сарказма и иронии. "
            "Используй ТОЛЬКО сдержанные эмодзи (свеча 🕯, разбитое сердце 💔). НИКАКИХ шуток."
        )
    else:
        tone_instruction = (
            "Твой стиль: дерзко, коротко, без воды. Добавь эмодзи (3-5 штук), чтобы текст был живым. "
            "Используй только тематические эмодзи. КАТЕГОРИЧЕСКИ НЕ ИСПОЛЬЗУЙ медицинские эмодзи."
        )

    prompt = (
        f"Ты — редактор канала 'MEDIA'. {tone_instruction}\n"
        "Перепиши эту новость на русский язык. Сделай это ОЧЕНЬ КОРОТКО: максимум 3-4 предложения.\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат ответа (СТРОГО!):\n"
        "Яркий заголовок с эмодзи.\n"
        "Пустая строка.\n"
        "Текст (2-3 предложения) с эмодзи.\n"
        "Пустая строка.\n"
        "Обязательно оформи ссылку так: '🔗 [Источник](ССЫЛКА)'\n"
        "Хэштеги: 3-4 штуки (через пробел).\n"
    )
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
            full_text = response.text.strip()
            
            if "http" in full_text and "[Источник]" not in full_text:
                full_text = re.sub(r"(https?://\S+)", r"🔗 [Источник](\1)", full_text)
                
            return full_text
        except Exception:
            time.sleep(3)
    return None

def send_to_telegram(text, image_url):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    
    # 1. Пробуем отправить текст (Telegram сам подтянет превью)
    try:
        url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
        payload_msg = {"chat_id": channel_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        resp = requests.post(url_msg, json=payload_msg, timeout=30)
        
        if resp.status_code == 200:
            print("Пост опубликован с превью!")
            return
    except Exception:
        pass

    # 2. Если что-то пошло не так, скачиваем картинку из RSS
    if image_url:
        try:
            img_response = requests.get(image_url, timeout=10)
            img_response.raise_for_status()
            img_data = img_response.content
            
            url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
            files = {'photo': ('image.jpg', BytesIO(img_data), 'image/jpeg')}
            data = {'chat_id': channel_id, 'caption': text, 'parse_mode': 'HTML'}
            resp_photo = requests.post(url_photo, data=data, files=files, timeout=30)
            
            if resp_photo.status_code == 200:
                print("Пост с картинкой из RSS опубликован!")
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")

if __name__ == "__main__":
    history = load_history()
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
        if is_duplicate(news['title'], history):
            print(f"Дубль пропущен: {news['title'][:30]}...")
            continue
            
        post_text = generate_post_text(news['title'], news['link'], news['description'])
        if post_text:
            send_to_telegram(post_text, news['image_url'])
            history.append(news['title'])
            
            if index < len(all_news) - 1:
                time.sleep(30)
    
    save_history(history)
    print("История сохранена.")
