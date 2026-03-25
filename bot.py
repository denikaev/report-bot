

if __name__ == "__main__":
          asyncio.run(main())
import asyncio
import logging
import os
import re
from datetime import datetime, date
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "7731756536:AAGCYLt_jpVsNCn1bfE0jvcAlo2a1ivgpPE")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

def parse_report(text: str) -> dict | None:
      if "#отчет_деникаев" not in text.lower():
                return None

      result = {
          "date": None, "done": [], "not_done": [], "tomorrow": [], "pending": [], "extra": [],
      }

    # Автоматическая дата если не указана
      date_match = re.search(r"#дата_(\d+)_(\d+)_(\d+)", text)
      if date_match:
                d, m, y = date_match.groups()
                result["date"] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
else:
        # Автоматически подставляем сегодняшнюю дату
          today = date.today()
          result["date"] = today.isoformat()

    lines = text.split("\n")
    section = None

    for line in lines:
              line = line.strip()
              if not line:
                            continue

              low = line.lower()
              if "отчет за день" in low and "завтра" not in low:
                            section = "today"
elif "ключевые задачи на завтра" in low:
            section = "tomorrow"
elif "доп задачи" in low:
            section = "extra"
elif "подвешенные" in low:
            section = "pending"
elif line.startswith("✅") and section == "today":
            result["done"].append(line[1:].strip())
elif line.startswith("❌") and section == "today":
            result["not_done"].append(line[1:].strip())
elif line.startswith("📌") and section == "tomorrow":
            result["tomorrow"].append(line[1:].strip())
elif line.startswith("❓") and section == "pending":
            result["pending"].append(line[1:].strip())
elif line.startswith("🚀") and section == "extra":
            result["extra"].append(line[1:].strip())

    return result

@dp.message(F.text.contains("#отчет_деникаев"))
async def handle_report(message: Message):
      parsed = parse_report(message.text)
      if not parsed:
                return

      chat_id = message.chat.id
      report_date = parsed["date"]

    db.save_chat_id(chat_id)
    db.save_report(
              chat_id=chat_id,
              report_date=report_date,
              done=parsed["done"],
              not_done=parsed["not_done"],
              tomorrow=parsed["tomorrow"],
              pending=parsed["pending"],
              extra=parsed["extra"],
    )

    done_count = len(parsed["done"])
    total = done_count + len(parsed["not_done"])
    pct = round(done_count / total * 100) if total else 0

    await message.reply(
              f"✅ Отчёт за {report_date} сохранён\n"
              f"📊 Выполнено: {done_count}/{total} ({pct}%)\n"
              f"📌 Задач на завтра: {len(parsed['tomorrow'])}\n"
              f"❓ Подвешенных: {len(parsed['pending'])}"
    )

@dp.message(Command("start"))
async def cmd_start(message: Message):
      db.save_chat_id(message.chat.id)
      await message.answer(
          "👋 Привет! Я помогаю с ежедневными отчётами.\n\n"
          "Просто пиши отчёты с хэштегом #отчет_деникаев — "
          "я буду их разбирать, считать статистику и напоминать о подвешенных задачах.\n\n"
          "Команды:\n"
          "/stats — статистика за неделю\n"
          "/pending — все подвешенные задачи\n"
          "/template — шаблон для отчёта на сегодня"
      )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
      rows = db.get_weekly_stats(message.chat.id)
      if not rows:
                await message.answer("Пока нет данных. Отправь хотя бы один отчёт.")
                return

      text = "📊 *Статистика за 7 дней:*\n\n"
      for r in rows:
                bar = "█" * (r["pct"] // 10) + "░" * (10 - r["pct"] // 10)
                text += f"`{r['date']}` {bar} {r['done']}/{r['total']} ({r['pct']}%)\n"

      total_done = sum(r["done"] for r in rows)
      total_all = sum(r["total"] for r in rows)
      avg = round(total_done / total_all * 100) if total_all else 0
      text += f"\n✨ Средний % за неделю: *{avg}%*"

    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("pending"))
async def cmd_pending(message: Message):
      tasks = db.get_pending_tasks(message.chat.id)
      if not tasks:
                await message.answer("❓ Подвешенных задач нет.")
                return

      text = "❓ *Подвешенные задачи:*\n\n"
      for t in tasks:
                days = (date.today() - date.fromisoformat(t["added_date"])).days
                age = f"({days}д)" if days > 0 else "(сегодня)"
                text += f"• {t['task']} {age}\n"

      await message.answer(text, parse_mode="Markdown")

def build_template(chat_id: int) -> str:
      today = date.today()
      d, m, y = today.day, today.month, today.year

    not_done = db.get_not_done_tasks(chat_id)
    pending = db.get_pending_tasks(chat_id)

    lines = [
              f"#отчет_деникаев",
              f"#дата_{d}_{m}_{y}",
              "",
              "• Отчет за день по ключевым задачам",
    ]

    # ✅❌ эмодзи для выбора - ты удаляешь ненужный
    for t in not_done:
              lines.append(f"✅❌{t}")

    lines += [
              "",
              "• Ключевые задачи на завтра",
              "📌",
              "",
              "• Доп задачи",
              "🚀",
              "",
              "• Подвешенные задачи",
    ]
    for t in pending:
              lines.append(f"❓{t['task']}")

    return "\n".join(lines)

@dp.message(Command("template"))
async def cmd_template(message: Message):
      await message.answer(build_template(message.chat.id))

async def send_morning_template():
      chat_ids = db.get_all_chat_ids()
      for chat_id in chat_ids:
                if not db.get_not_done_tasks(chat_id) and not db.get_pending_tasks(chat_id):
                              continue
                          text = "☀️ Доброе утро! Шаблон на сегодня:\n\n" + build_template(chat_id)
                await bot.send_message(chat_id, text)

  async def send_pending_reminder():
        chat_ids = db.get_all_chat_ids()
        for chat_id in chat_ids:
                  tasks = db.get_old_pending_tasks(chat_id, days=7)
                  if not tasks:
                                continue
                            text = "⚠️ *Старые подвешенные задачи (7+ дней):*\n\n"
                  for t in tasks:
                                days = (date.today() - date.fromisoformat(t["added_date"])).days
                                text += f"• {t['task']} — висит {days} дней\n"
                            await bot.send_message(chat_id, text, parse_mode="Markdown")

    async def main():
          db.init_db()

    scheduler.add_job(send_morning_template, "cron", hour=9, minute=0)
    scheduler.add_job(send_pending_reminder, "cron", day_of_week="fri", hour=18, minute=0)
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
      asyncio.run(main())
