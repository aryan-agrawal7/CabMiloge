import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import sqlite3
import os
import re
from datetime import datetime, timedelta
import pytz

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

DOCKER_DB_PATH = '/app/sqllite_volume/cabmates.db'
# Fallback path for local development
LOCAL_DB_PATH = 'sqllite_volume/cabmates.db'
DB_PATH = DOCKER_DB_PATH if os.path.exists(DOCKER_DB_PATH) else LOCAL_DB_PATH
LOGIN, REGISTRATION = range(2)
local_timezone = pytz.timezone('Asia/Kolkata')

def get_db_connection():
    """Create a connection to the database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_batch(roll):
    """Extract batch information from roll number"""
    roll = str(roll)
    year = roll[:4]
    rem = roll[4:]
    batch = year
    if (rem[0] in ('7', '8')) or rem[:3] == "900":
        batch = "PhD"+batch
    elif (rem[:2] in ('10', '11')) or rem[:3] == "909":
        batch = "UG"+batch
    elif (rem[:2] in ('20', '21')):
        batch = "PG"+batch
    elif (rem[:2] == '12'):
        batch = "LE"+batch
    return batch

def is_user_registered(telegram_id):
    """Check if user is registered in the system"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM Login WHERE TelegramID = ?', (telegram_id,))
    user = cursor.fetchone()
    
    conn.close()
    return user is not None

def get_user_info(telegram_id):
    """Get user information from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM Login WHERE TelegramID = ?', (telegram_id,))
    user = cursor.fetchone()
    
    conn.close()
    return user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    
    if is_user_registered(user.id):
        user_info = get_user_info(user.id)
        await update.message.reply_text(
            f"Welcome back, {user_info['Fname']} {user_info['Lname']}!\n\n"
            "You can use the following commands:\n"
            "/pool - View your active ride requests and potential matches\n"
            "/cancel - Cancel your most recent request\n"
            "/help - Show help information\n\n"
            "Or you can create a new ride request using the format:\n"
            "C2A DD/MM/YY HH:MM - Request a ride from Campus to Airport\n"
            "A2C DD/MM/YY HH:MM - Request a ride from Airport to Campus\n"
            "S2A DD/MM/YY HH:MM - Request a ride from Secunderabad to Airport\n"
            "A2S DD/MM/YY HH:MM - Request a ride from Airport to Secunderabad\n"
            "R2A DD/MM/YY HH:MM - Request a ride from Railway Station to Airport\n"
            "A2R DD/MM/YY HH:MM - Request a ride from Airport to Railway Station"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"Hello {user.first_name}! Welcome to the CabMiloge Telegram Bot.\n\n"
            "To use this service, you need to register first.\n"
            "Please provide your details in the following format:\n\n"
            "register FirstName LastName Email RollNo PhoneNo\n\n"
            "Example: register John Doe john.doe@example.com 2020501001 9876543210"
        )
        return LOGIN

async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Register a new user"""
    user = update.effective_user
    text = update.message.text
    
    if not text.lower().startswith('register '):
        await update.message.reply_text(
            "Please use the format: register FirstName LastName Email RollNo PhoneNo\n\n"
            "Example: register John Doe john.doe@example.com 2020501001 9876543210"
        )
        return LOGIN
    
    try:
        parts = text.split(' ', 1)[1].split()
        if len(parts) < 5:
            await update.message.reply_text("Not enough information provided. Please try again.")
            return LOGIN
        
        fname = parts[0]
        lname = parts[1]
        email = parts[2]
        roll = parts[3]
        phone = parts[4]
        
        # Generate UID from email (using the part before @)
        uid = email.split('@')[0]
        
        # Get batch
        batch = get_batch(roll)
        
        # Add user to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user with email/uid already exists
        cursor.execute('SELECT * FROM Login WHERE Email = ? OR Uid = ?', (email, uid))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # Update the existing record with Telegram ID
            cursor.execute(
                'UPDATE Login SET TelegramID = ? WHERE Uid = ?',
                (user.id, uid)
            )
            await update.message.reply_text(
                f"Your account has been linked to your Telegram ID.\n\n"
                "You can now use the following commands:\n"
                "/pool - View your active ride requests and potential matches\n"
                "/cancel - Cancel your most recent request\n"
                "/help - Show help information"
            )
        else:
            # Insert new user
            cursor.execute(
                'INSERT INTO Login (Fname, Lname, Email, RollNo, Uid, Batch, Gender, PhoneNo, TelegramID) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (fname, lname, email, roll, uid, batch, "", phone, user.id)
            )
            await update.message.reply_text(
                f"Registration successful, {fname}!\n\n"
                "You can now use the following commands:\n"
                "/pool - View your active ride requests and potential matches\n"
                "/cancel - Cancel your most recent request\n"
                "/help - Show help information"
            )
        
        conn.commit()
        conn.close()
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await update.message.reply_text(
            "An error occurred during registration. Please try again.\n\n"
            "Use the format: register FirstName LastName Email RollNo PhoneNo"
        )
        return LOGIN

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user = update.effective_user
    
    if not is_user_registered(user.id):
        await update.message.reply_text(
            "You need to register first. Use /start to begin the registration process."
        )
        return
    
    await update.message.reply_text(
        "CabMiloge Bot Help:\n\n"
        "Commands:\n"
        "/start - Start the bot and register if needed\n"
        "/help - Show this help message\n"
        "/pool - View your active ride requests and potential matches\n"
        "/cancel - Cancel your most recent request\n\n"
        "Creating a ride request:\n"
        "Use one of the following formats:\n"
        "C2A DD/MM/YY HH:MM - Request a ride from Campus to Airport\n"
        "A2C DD/MM/YY HH:MM - Request a ride from Airport to Campus\n"
        "S2A DD/MM/YY HH:MM - Request a ride from Secunderabad to Airport\n"
        "A2S DD/MM/YY HH:MM - Request a ride from Airport to Secunderabad\n"
        "R2A DD/MM/YY HH:MM - Request a ride from Railway Station to Airport\n"
        "A2R DD/MM/YY HH:MM - Request a ride from Airport to Railway Station\n\n"
        "You will receive notifications about potential matches ±30 minutes from your requested time."
    )

async def pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all active ride requests and potential matches"""
    user = update.effective_user
    
    if not is_user_registered(user.id):
        await update.message.reply_text(
            "You need to register first. Use /start to begin the registration process."
        )
        return
    
    user_info = get_user_info(user.id)
    uid = user_info['Uid']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    current_datetime = datetime.now(local_timezone).strftime('%Y-%m-%d %H:%M:%S')
    
    # Get user's upcoming rides
    cursor.execute('''
        SELECT * FROM fromCampus 
        WHERE Uid = ? AND DateTime > ?
        ORDER BY DateTime ASC
    ''', (uid, current_datetime))
    from_campus_rides = cursor.fetchall()
    
    cursor.execute('''
        SELECT * FROM toCampus 
        WHERE Uid = ? AND DateTime > ?
        ORDER BY DateTime ASC
    ''', (uid, current_datetime))
    to_campus_rides = cursor.fetchall()
    
    if not from_campus_rides and not to_campus_rides:
        await update.message.reply_text("You have no active ride requests.")
        conn.close()
        return
    message = "Your active ride requests:\n\n"
    if from_campus_rides:
        message += "FROM CAMPUS:\n"
        for ride in from_campus_rides:
            date_time = datetime.strptime(ride['DateTime'], '%Y-%m-%d %H:%M:%S')
            formatted_date = date_time.strftime('%d/%m/%y %H:%M')
            message += f"• To {ride['Station']} on {formatted_date}\n"
            
            # Find potential matches (±30 minutes)
            match_start = (date_time - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            match_end = (date_time + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT f.*, l.Fname, l.Lname, l.PhoneNo, l.Email 
                FROM fromCampus f
                JOIN Login l ON f.Uid = l.Uid
                WHERE f.Station = ? 
                  AND f.DateTime BETWEEN ? AND ?
                  AND f.Uid != ?
                ORDER BY f.DateTime ASC
            ''', (ride['Station'], match_start, match_end, uid))
            
            matches = cursor.fetchall()
            if matches:
                message += "  Potential matches:\n"
                for match in matches:
                    match_date_time = datetime.strptime(match['DateTime'], '%Y-%m-%d %H:%M:%S')
                    match_formatted = match_date_time.strftime('%d/%m/%y %H:%M')
                    message += f"  - {match['Fname']} {match['Lname']} at {match_formatted}\n"
                    message += f"    Contact: {match['PhoneNo']} | {match['Email']}\n"
            else:
                message += "  No matches found yet\n"
            
            message += "\n"
    
    # To Campus rides
    if to_campus_rides:
        message += "TO CAMPUS:\n"
        for ride in to_campus_rides:
            date_time = datetime.strptime(ride['DateTime'], '%Y-%m-%d %H:%M:%S')
            formatted_date = date_time.strftime('%d/%m/%y %H:%M')
            message += f"• From {ride['Station']} on {formatted_date}\n"
            
            # Find potential matches (±30 minutes)
            match_start = (date_time - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            match_end = (date_time + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT t.*, l.Fname, l.Lname, l.PhoneNo, l.Email 
                FROM toCampus t
                JOIN Login l ON t.Uid = l.Uid
                WHERE t.Station = ? 
                  AND t.DateTime BETWEEN ? AND ?
                  AND t.Uid != ?
                ORDER BY t.DateTime ASC
            ''', (ride['Station'], match_start, match_end, uid))
            
            matches = cursor.fetchall()
            if matches:
                message += "  Potential matches:\n"
                for match in matches:
                    match_date_time = datetime.strptime(match['DateTime'], '%Y-%m-%d %H:%M:%S')
                    match_formatted = match_date_time.strftime('%d/%m/%y %H:%M')
                    message += f"  - {match['Fname']} {match['Lname']} at {match_formatted}\n"
                    message += f"    Contact: {match['PhoneNo']} | {match['Email']}\n"
            else:
                message += "  No matches found yet\n"
            
            message += "\n"
    
    conn.close()
    await update.message.reply_text(message)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the most recent ride request"""
    user = update.effective_user
    
    if not is_user_registered(user.id):
        await update.message.reply_text(
            "You need to register first. Use /start to begin the registration process."
        )
        return
    
    user_info = get_user_info(user.id)
    uid = user_info['Uid']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    current_datetime = datetime.now(local_timezone).strftime('%Y-%m-%d %H:%M:%S')
    
    # Find the most recent ride request
    cursor.execute('''
        SELECT 'fromCampus' as direction, BookingID, DateTime, Station 
        FROM fromCampus 
        WHERE Uid = ? AND DateTime > ?
        UNION ALL
        SELECT 'toCampus' as direction, BookingID, DateTime, Station 
        FROM toCampus 
        WHERE Uid = ? AND DateTime > ?
        ORDER BY DateTime DESC
        LIMIT 1
    ''', (uid, current_datetime, uid, current_datetime))
    
    latest_ride = cursor.fetchone()
    
    if not latest_ride:
        await update.message.reply_text("You have no active ride requests to cancel.")
        conn.close()
        return
    
    # Delete the ride
    if latest_ride['direction'] == 'fromCampus':
        cursor.execute('DELETE FROM fromCampus WHERE BookingID = ?', (latest_ride['BookingID'],))
        direction = "from Campus to " + latest_ride['Station']
    else:
        cursor.execute('DELETE FROM toCampus WHERE BookingID = ?', (latest_ride['BookingID'],))
        direction = "from " + latest_ride['Station'] + " to Campus"
    
    conn.commit()
    conn.close()
    
    date_time = datetime.strptime(latest_ride['DateTime'], '%Y-%m-%d %H:%M:%S')
    formatted_date = date_time.strftime('%d/%m/%y %H:%M')
    
    await update.message.reply_text(
        f"Your ride request {direction} on {formatted_date} has been cancelled."
    )

async def process_ride_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process ride request messages"""
    user = update.effective_user
    
    if not is_user_registered(user.id):
        await update.message.reply_text(
            "You need to register first. Use /start to begin the registration process."
        )
        return
    
    text = update.message.text.strip().upper()
    ride_pattern = r'^(C2A|A2C|S2A|A2S|R2A|A2R)\s+(\d{2}/\d{2}/\d{2})\s+(\d{1,2}:\d{2})$'
    match = re.match(ride_pattern, text)
    
    if not match:
        await update.message.reply_text(
            "Invalid format. Please use:\n"
            "C2A DD/MM/YY HH:MM - Campus to Airport\n"
            "A2C DD/MM/YY HH:MM - Airport to Campus\n"
            "S2A DD/MM/YY HH:MM - Secunderabad to Airport\n"
            "A2S DD/MM/YY HH:MM - Airport to Secunderabad\n"
            "R2A DD/MM/YY HH:MM - Railway Station to Airport\n"
            "A2R DD/MM/YY HH:MM - Airport to Railway Station"
        )
        return
    
    direction = match.group(1)
    date_str = match.group(2)
    time_str = match.group(3)
    try:
        day, month, year = map(int, date_str.split('/'))
        hour, minute = map(int, time_str.split(':'))
        if year < 100:
            year += 2000
        
        ride_date = datetime(year, month, day, hour, minute)
        if ride_date < datetime.now():
            await update.message.reply_text("Cannot create ride requests for past dates.")
            return
            
        date_time_str = ride_date.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        await update.message.reply_text("Invalid date or time format. Please use DD/MM/YY HH:MM")
        return
    
    # Define stations based on direction
    from_station = ""
    to_station = ""
    is_from_campus = False
    
    if direction == "C2A":
        from_station = "IIIT Campus"
        to_station = "Airport"
        is_from_campus = True
    elif direction == "A2C":
        from_station = "Airport"
        to_station = "IIIT Campus"
    elif direction == "S2A":
        from_station = "Secunderabad"
        to_station = "Airport"
        is_from_campus = True
    elif direction == "A2S":
        from_station = "Airport"
        to_station = "Secunderabad"
    elif direction == "R2A":
        from_station = "Railway Station"
        to_station = "Airport"
        is_from_campus = True
    elif direction == "A2R":
        from_station = "Airport"
        to_station = "Railway Station"
    user_info = get_user_info(user.id)
    uid = user_info['Uid']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if is_from_campus:
            cursor.execute(
                'INSERT INTO fromCampus (Uid, DateTime, Station) VALUES (?, ?, ?)',
                (uid, date_time_str, to_station)
            )
        else:
            cursor.execute(
                'INSERT INTO toCampus (Uid, DateTime, Station) VALUES (?, ?, ?)',
                (uid, date_time_str, from_station)
            )
        
        conn.commit()
        
        # Check for potential matches
        match_start = (ride_date - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        match_end = (ride_date + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        
        if is_from_campus:
            cursor.execute('''
                SELECT f.*, l.Fname, l.Lname, l.PhoneNo, l.Email, l.TelegramID 
                FROM fromCampus f
                JOIN Login l ON f.Uid = l.Uid
                WHERE f.Station = ? 
                  AND f.DateTime BETWEEN ? AND ?
                  AND f.Uid != ?
                ORDER BY f.DateTime ASC
            ''', (to_station, match_start, match_end, uid))
        else:
            cursor.execute('''
                SELECT t.*, l.Fname, l.Lname, l.PhoneNo, l.Email, l.TelegramID 
                FROM toCampus t
                JOIN Login l ON t.Uid = l.Uid
                WHERE t.Station = ? 
                  AND t.DateTime BETWEEN ? AND ?
                  AND t.Uid != ?
                ORDER BY t.DateTime ASC
            ''', (from_station, match_start, match_end, uid))
        
        matches = cursor.fetchall()
        
        # Response message
        response = f"Ride request added: {from_station} to {to_station} on {date_str} at {time_str}\n\n"
        
        if matches:
            response += "Potential matches found:\n"
            for match in matches:
                match_date_time = datetime.strptime(match['DateTime'], '%Y-%m-%d %H:%M:%S')
                match_formatted = match_date_time.strftime('%d/%m/%y %H:%M')
                response += f"- {match['Fname']} {match['Lname']} at {match_formatted}\n"
                response += f"  Contact: {match['PhoneNo']} | {match['Email']}\n"
                
                # Notify the other user if they have Telegram ID
                if match['TelegramID']:
                    try:
                        await context.bot.send_message(
                            chat_id=match['TelegramID'],
                            text=f"New ride match found!\n\n"
                                 f"{user_info['Fname']} {user_info['Lname']} is also traveling from "
                                 f"{from_station} to {to_station} on {date_str} at {time_str}.\n"
                                 f"Contact: {user_info['PhoneNo']} | {user_info['Email']}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification: {e}")
        else:
            response += "No potential matches found yet. You'll be notified when someone matches your time slot."
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Error creating ride request: {e}")
        await update.message.reply_text("An error occurred while processing your request. Please try again.")
    
    finally:
        conn.close()

def main() -> None:
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_user)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pool", pool_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, process_ride_request
    ))
    application.run_polling()

if __name__ == '__main__':
    main()