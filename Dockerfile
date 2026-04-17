# 1. ვიყენებთ პითონის სტაბილურ და მსუბუქ ვერსიას
FROM python:3.10-slim

# 2. ვქმნით სამუშაო საქაღალდეს კონტეინერში
WORKDIR /app

# 3. სისტემური განახლება და საჭირო ხელსაწყოები
# დავამატოთ sqlite3, რადგან ბოტი sacra_guard_data.db-ს იყენებს
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 4. ბიბლიოთეკების ინსტალაცია
# (უმჯობესია Flask და discord.py პირდაპირ აქ ეწეროს, როგორც შენთანაა)
RUN pip install --no-cache-dir discord.py Flask requests python-dotenv

# 5. ვაკოპირებთ შენს მთლიან კოდს კონტეინერში
# (დარწმუნდი, რომ main_integrated.py იმავე პაპკაშია, სადაც ეს დოკერფაილი)
COPY . .

# 6. პორტის გამოცხადება Flask-ისთვის (Keep Alive)
EXPOSE 8080

# 7. ბოტის გაშვება
# PYTHONUNBUFFERED=1 ეხმარება ლოგების რეალურ დროში დანახვაში
ENV PYTHONUNBUFFERED=1
CMD ["python", "main_integrated.py"]