import requests
import json
import os
import re
import telegram
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, CommandHandler, filters, CallbackContext

# Настройки Telegram
from data import TELEGRAM_TOKEN, ADMIN_GROUP_ID, MATTERMOST_WEBHOOK_ACTIV, MATTERMOST_WEBHOOK_SELL, MATTERMOST_WEBHOOK_SPEND

# Путь к файлу для хранения данных о топиках
DATA_FILE = 'user_topics.json'

# Загрузка данных из файла
def load_user_topics():
    """
    Загружает данные о топиках из файла.
    """
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as file:
            return json.load(file)
    return {}

# Сохранение данных в файл
def save_user_topics(user_topics):
    """
    Сохраняет данные о топиках в файл.
    """
    with open(DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(user_topics, file, ensure_ascii=False, indent=4)

# Словарь для хранения контекста диалогов
user_topics = load_user_topics()

# Словарь для хранения промежуточных данных пользователей
user_data = {}  # user_id -> {"step": str, "data": dict}

# Шаблоны клавиатур
# KEYBOARD_PARTNER = [['ФинДоставка'], ['ЕФин'], ['СК']]
KEYBOARD_SALE_ACTIVATION = [['продажа'], ['активация'], ['активация + продажа'], ['спенд'], ['проверить статус запроса']]
KEYBOARD_MBB_KSN = [['МББ'], ['КСН']]
KEYBOARD_MBB_KSN_NOTHING = [['МББ'], ['КСН'], ['Без продажи']]

async def send_to_mm(mattermost_webhook_url, message):
    """
    Отправляет сообщение в мм
    """
    payload = {
        'text': message
    }
    response = requests.post(mattermost_webhook_url, json=payload)
    if response.status_code != 200:
        print(f"Ошибка при отправке в Mattermost: {response.text}")

async def start(update: Update, context: CallbackContext):
    """
    Команда /start для начала работы с ботом.
    """
    user_id = update.message.from_user.id
    user_data[user_id] = {"step": "enter_code", "data": {}}
    await update.message.reply_text(
        "Введите лид вида 1-XXXXXXX:"
    )

async def handle_user_message(update: Update, context: CallbackContext):
    """
    Обрабатывает сообщения от пользователей.
    """
    message = update.message
    user_id = message.from_user.id
    text = message.text

    if user_id not in user_data:
        await message.reply_text(
            """Чтобы начать, используйте команду /start.
            \nЗапросы обрабатываются по будням с 5:00 до 19:00 по МСК"""
            )
        return

    step = user_data[user_id]["step"]

    if step == "enter_code":
        # Проверяем, соответствует ли код шаблону "1-XXXXXXX"
        if re.match(r"^1-[A-Za-z0-9]{7}$", text):
            user_data[user_id]["data"]["code"] = text
            user_data[user_id]["step"] = "choose_action"
            await message.reply_text(
                "Выберите действие:",
                reply_markup=ReplyKeyboardMarkup(KEYBOARD_SALE_ACTIVATION, one_time_keyboard=True)
            )
        else:
            await message.reply_text("Неверный лид. Введите лид в формате 1-XXXXXXX.")
            
    # elif step == "partner":        
    #     if text in ['ФинДоставка', 'ЕФин', 'СК']:
    #         user_data[user_id]["data"]["partner"] = text
    #         user_data[user_id]["step"] = "choose_action"
    #         await message.reply_text(
    #             "Выберите действие:",
    #             reply_markup=ReplyKeyboardMarkup(KEYBOARD_SALE_ACTIVATION, one_time_keyboard=True)
    #         )
    #     else:
    #         await message.reply_text("Выберите партнёра из предложенных вариантов.")

    elif step == "choose_action":
        # Проверяем, что выбрано "продажа" или "активация"
        if text in ["продажа", "активация", "активация + продажа", "спенд", "проверить статус запроса"]:
            user_data[user_id]["data"]["action"] = text
            if text == "продажа":
                user_data[user_id]["step"] = "choose_product"
                await message.reply_text(
                    "Выберите продукт:",
                    reply_markup=ReplyKeyboardMarkup(KEYBOARD_MBB_KSN, one_time_keyboard=True)
                )
            elif text == "активация":
                user_data[user_id]["step"] = "choose_product"
                await message.reply_text(
                    "Выберите продукт:",
                    reply_markup=ReplyKeyboardMarkup(KEYBOARD_MBB_KSN_NOTHING, one_time_keyboard=True)
                )
            elif text == "активация + продажа":
                user_data[user_id]["step"] = "choose_product"
                await message.reply_text(
                    "Выберите продукт:",
                    reply_markup=ReplyKeyboardMarkup(KEYBOARD_MBB_KSN, one_time_keyboard=True)
                )
            elif text == "спенд":
                user_data[user_id]["step"] = "final"
                await finalize_message(user_id, message, context)  # Передаём context
            
            elif text == "проверить статус запроса":
                user_data[user_id]["step"] = "final"
                await finalize_message(user_id, message, context)  # Передаём context

            else:
                user_data[user_id]["step"] = "final"
                await finalize_message(user_id, message, context)  # Передаём context

    elif step == "choose_product":
        # Проверяем, что выбрано "МББ" или "КСН"
        if text in ["МББ", "КСН"]:
            user_data[user_id]["data"]["product"] = text
            user_data[user_id]["step"] = "final"
            await finalize_message(user_id, message, context)  # Передаём context
        elif text in ["Без продажи"]:
            user_data[user_id]["step"] = "final"
            await finalize_message(user_id, message, context)  # Передаём context
        else:
            await message.reply_text("Выберите продукт из предложенных вариантов.")

async def finalize_message(user_id: int, message: telegram.Message, context: CallbackContext):
    """
    Формирует итоговое сообщение и отправляет его в топик.
    """
    data = user_data[user_id]["data"]
    username = message.from_user.username or message.from_user.first_name

    # Формируем сообщение по шаблону
    final_message = f"{data['code']}\n{data['action']}"
    if "product" in data:
        final_message += f" {data['product']}"

    # Отправляем сообщение в топик
    topic_id = await find_or_create_topic(context.bot, username, user_id)
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=final_message,
        message_thread_id=topic_id
    )
    # Отправляем сообщение в ММ
    if "активация" in final_message:
        await send_to_mm(mattermost_webhook_url=MATTERMOST_WEBHOOK_ACTIV, message=final_message)
    elif "спенд" in final_message:
        await send_to_mm(mattermost_webhook_url=MATTERMOST_WEBHOOK_SPEND, message=final_message)
    else:
        await send_to_mm(mattermost_webhook_url=MATTERMOST_WEBHOOK_SELL, message=final_message)

    # Очищаем данные пользователя
    del user_data[user_id]

    await message.reply_text(
        "Сообщение отправлено.",
        reply_markup=ReplyKeyboardRemove()
    )

async def create_topic(bot: telegram.Bot, username: str):
    """
    Создаёт новый топик в группе администраторов.
    """
    response = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=username)
    return response.message_thread_id

async def find_or_create_topic(bot: telegram.Bot, username: str, user_id: int):
    """
    Ищет топик по имени пользователя или создаёт новый, если его нет.
    """
    if str(user_id) in user_topics:
        return user_topics[str(user_id)]

    topic_id = await create_topic(bot, username)
    user_topics[str(user_id)] = topic_id
    save_user_topics(user_topics)
    return topic_id

async def handle_admin_reply(update: Update, context: CallbackContext):
    """
    Обрабатывает ответы администраторов и пересылает их обратно пользователю.
    """
    message = update.message
    reply_to_message = message.reply_to_message

    if not reply_to_message:
        return

    topic_id = reply_to_message.message_thread_id
    user_id = None

    for uid, tid in user_topics.items():
        if int(tid) == topic_id:
            user_id = int(uid)
            break

    if not user_id:
        print("Пользователь не найден.")
        return

    await context.bot.send_message(chat_id=user_id, text=message.text)

def main():
    # Создаем и настраиваем бота
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler('start', start))

    # Обработчик сообщений от пользователей
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_user_message))

    # Обработчик ответов администраторов в топиках
    application.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID) & filters.REPLY, handle_admin_reply))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()