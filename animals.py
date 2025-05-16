import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# ---------------- CONFIG ----------------
URL = "https://pasadenahumane.org/adopt/view-pets/dogs/"
DATA_FILE = "yesterday_dogs.json"

EMAIL_SENDER = "dogupdate265@gmail.com"
EMAIL_RECEIVER = "matthew@biofare.org"
EMAIL_SUBJECT = "🐶 Pasadena Humane Daily Dog Report"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_PASSWORD = "awig bbbg xtni ckel"  # Use Gmail app password
# ----------------------------------------

def scrape_dogs():
    logging.info("Scraping main dog listing page...")
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    dog_entries = soup.find_all('a', href=True)
    dogs = []

    for a in dog_entries:
        text = a.get_text(separator=" ").strip()
        if not text or '|' not in text:
            continue
        parts = [part.strip() for part in text.split('|')]
        if len(parts) != 4:
            continue
        name_breed = parts[0]
        age = parts[1]
        sex = parts[2]
        id_and_fee = parts[3]
        animal_id = id_and_fee.split()[0]
        tokens = name_breed.split()
        name = tokens[0]
        breed = " ".join(tokens[1:]) or "Unknown"
        detail_url = a['href']

        detail_response = requests.get(detail_url)
        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
        logging.info(f"Fetched detail page for {name}")
        kennel_info = detail_soup.find(string=lambda text: text and "Kennel" in text)
        kennel = kennel_info.split(":")[-1].strip() if kennel_info else "Unknown"

        img_tag = detail_soup.find('img', alt=name)
        photo_url = img_tag['src'] if img_tag else None

        image_dir = os.path.join(os.path.dirname(__file__), "images")
        os.makedirs(image_dir, exist_ok=True)
        photo_path = None
        if photo_url:
            try:
                img_data = requests.get(photo_url).content
                ext = os.path.splitext(photo_url)[1].split("?")[0] or ".jpg"
                photo_path = os.path.join(image_dir, f"{animal_id}{ext}")
                with open(photo_path, "wb") as img_file:
                    img_file.write(img_data)
            except Exception as e:
                logging.warning(f"Failed to download image for {name} (ID: {animal_id}): {e}")

        intake_info = detail_soup.find(string=lambda text: text and "Intake Date" in text)
        intake_date_str = intake_info.split(":")[-1].strip() if intake_info else None
        intake_date = intake_date_str  # save raw string for now

        dogs.append({
            "id": animal_id,
            "name": name,
            "breed": breed,
            "age": age,
            "sex": sex,
            "detail_url": detail_url,
            "kennel": kennel,
            "photo_url": photo_url,
            "photo_path": photo_path,
            "intake_date": intake_date
        })
        logging.info(f"Processing dog: {name} (ID: {animal_id})")
    return dogs

def load_yesterday_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_today_data(dogs):
    with open(DATA_FILE, 'w') as f:
        json.dump(dogs, f)

def compare_dogs(today, yesterday):
    from dateutil import parser as date_parser
    today_dict = {dog['id']: dog for dog in today}
    yest_dict = {dog['id']: dog for dog in yesterday}

    new_dogs = [dog for id, dog in today_dict.items() if id not in yest_dict]
    adopted_dogs = []
    for id, dog in yest_dict.items():
        if id not in today_dict:
            intake = dog.get("intake_date")
            duration_str = ""
            if intake:
                try:
                    intake_dt = date_parser.parse(intake)
                    delta = datetime.now() - intake_dt
                    months, days = divmod(delta.days, 30)
                    duration_str = f"{months} months, {days} days"
                except Exception:
                    duration_str = "Unknown"
            dog["duration"] = duration_str
            adopted_dogs.append(dog)

    updated_photos = []
    for id in today_dict:
        if id in yest_dict and today_dict[id].get("photo_url") != yest_dict[id].get("photo_url"):
            entry = today_dict[id].copy()
            entry["old_photo_url"] = yest_dict[id].get("photo_url")
            entry["old_photo_path"] = yest_dict[id].get("photo_path")
            updated_photos.append(entry)
    logging.info(f"Found {len(new_dogs)} new dogs, {len(adopted_dogs)} adopted, {len(updated_photos)} with updated photos.")
    return new_dogs, adopted_dogs, updated_photos

def generate_html_report(new_dogs, adopted_dogs, updated_photos):
    html = f"<html><body><h2>🐾 Pasadena Humane Dog Report – {datetime.now().strftime('%B %d, %Y')}</h2>"
    html += f"<p><strong>{len(new_dogs)} new</strong> dogs, <strong>{len(adopted_dogs)} adopted</strong>.</p>"

    if new_dogs:
        html += "<h3>New Arrivals</h3>"
        for dog in new_dogs:
            html += f"""
            <div style='margin-bottom:15px;'>
                <a href='{dog['detail_url']}'><strong>{dog['name']}</strong></a><br>
                Breed: {dog['breed']}<br>
                Age: {dog['age']}<br>
                Sex: {dog['sex']}<br>
                ID: {dog['id']}<br>
                Kennel: {dog['kennel']}
            </div>
            """

    if adopted_dogs:
        html += "<h3>Adopted Dogs</h3><ul>"
        for dog in adopted_dogs:
            html += f"<li><strong>{dog['name']}</strong> (ID: {dog['id']}) – Adopted after {dog.get('duration', 'Unknown')}</li>"
        html += "</ul>"

    if updated_photos:
        html += "<h3>Updated Photos</h3>"
        for dog in updated_photos:
            html += f"""
            <div style='margin-bottom:20px;'>
                <strong>{dog['name']}</strong> (ID: {dog['id']}) – New photo detected<br>
                <div style='display:flex;gap:10px;'>
                    <div>
                        <p style='margin:0;font-size:small;'>Before:</p>
                        <img src='cid:{dog['id']}_old' style='width:100px;'>
                    </div>
                    <div>
                        <p style='margin:0;font-size:small;'>After:</p>
                        <img src='cid:{dog['id']}_new' style='width:100px;'>
                    </div>
                </div>
            </div>
            """

    html += "</body></html>"
    return html

def send_email(html_content):
    logging.info("Sending email report...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = EMAIL_SUBJECT
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER

    part1 = MIMEText("Daily Pasadena Humane dog report (HTML format).", 'plain')
    part2 = MIMEText(html_content, 'html')
    msg.attach(part1)
    msg.attach(part2)

    # Attach images for old and new photos
    # Load yesterday's dogs and today's updated photos for attachments
    try:
        with open(DATA_FILE, 'r') as f:
            yesterday_dogs = json.load(f)
    except Exception:
        yesterday_dogs = []
    # Attach old images
    for dog in yesterday_dogs:
        if dog.get("photo_path"):
            try:
                with open(dog["photo_path"], "rb") as img:
                    img_data = img.read()
                from email.mime.image import MIMEImage
                image = MIMEImage(img_data)
                image.add_header('Content-ID', f"<{dog['id']}_old>")
                msg.attach(image)
            except Exception as e:
                logging.warning(f"Failed to attach old image for {dog.get('name')} (ID: {dog.get('id')}): {e}")
    # Attach new images for updated photos (if any)
    try:
        # Get updated_photos from globals (should be present in main flow)
        updated_photos = globals().get("updated_photos", [])
    except Exception:
        updated_photos = []
    for dog in updated_photos:
        if dog.get("photo_path"):
            try:
                with open(dog["photo_path"], "rb") as img:
                    img_data = img.read()
                from email.mime.image import MIMEImage
                image = MIMEImage(img_data)
                image.add_header('Content-ID', f"<{dog['id']}_new>")
                msg.attach(image)
            except Exception as e:
                logging.warning(f"Failed to attach new image for {dog.get('name')} (ID: {dog.get('id')}): {e}")

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL_SENDER, SMTP_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

# -------- Main flow --------
logging.info("Starting daily scrape process...")
today_dogs = scrape_dogs()
yesterday_dogs = load_yesterday_data()
new_dogs, adopted_dogs, updated_photos = compare_dogs(today_dogs, yesterday_dogs)
logging.info("Saving today’s data...")
save_today_data(today_dogs)
logging.info("Generating HTML report...")
html_report = generate_html_report(new_dogs, adopted_dogs, updated_photos)
send_email(html_report)
logging.info("Done.")