from flask import Flask, render_template, request,redirect,session,jsonify,send_from_directory,url_for
import sqlite3
from cas import CASClient
from urllib.parse import quote_plus
from cryptography.fernet import Fernet
import os
from functools import cmp_to_key
from datetime import datetime
import pytz


key = Fernet.generate_key()

BASE_URL = os.getenv('BASE_URL', 'http://172.22.0.2:80')
SUBPATH = os.getenv('SUBPATH', '')

SECRET_KEY = os.getenv('SECRET_KEY',os.urandom(24))
CAS_SERVER_URL = os.getenv('CAS_SERVER_URL', 'https://login.iiit.ac.in/cas/')
SERVICE_URL = os.getenv('SERVICE_URL', f'{BASE_URL}{SUBPATH}/Get_Auth')
REDIRECT_URL = os.getenv('REDIRECT_URL', f'{BASE_URL}{SUBPATH}/Get_Auth')

app = Flask(__name__)
app.secret_key = SECRET_KEY

cas_client = CASClient(
    version=3,
    service_url=f"{SERVICE_URL}?next={quote_plus(REDIRECT_URL)}",
    server_url=CAS_SERVER_URL,
)

# Database Setup
conn = sqlite3.connect('sqllite_volume/cabmates.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Login (
        Fname TEXT,
        Lname TEXT,
        Email TEXT,
        RollNo TEXT,
        Uid TEXT PRIMARY KEY,
        Batch TEXT,
        Gender TEXT,
        PhoneNo TEXT,
        TelegramID TEXT
    )
''')


cursor.execute('''CREATE TABLE IF NOT EXISTS fromCampus (BookingID INTEGER PRIMARY KEY AUTOINCREMENT, Uid TEXT, DateTime DATETIME, Station TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS toCampus (BookingID INTEGER PRIMARY KEY AUTOINCREMENT, Uid TEXT, DateTime DATETIME, Station TEXT)''')

# Database Setup End


local_timezone = pytz.timezone('Asia/Kolkata')

def compare_datetime(entry1, entry2):
    if entry1[2] < entry2[2]:
        return -1
    elif entry1[2] > entry2[2]:
        return 1
    else:
        return 0
    
def sort_by_datetime(entries):
    entries.sort(key=cmp_to_key(compare_datetime))
    return entries

@app.route(f'{SUBPATH}/')
def LogIn():
    if session:
        return redirect(f'{SUBPATH}/upcomingTravels')
    return render_template('LogIn.html', subpath=SUBPATH)


@app.route(f'{SUBPATH}/Get_Auth', methods=['POST', 'GET'])
def Get_Auth():
    if request.method == 'POST':
        cas_login_url = cas_client.get_login_url()
        return redirect(cas_login_url)
    else:
        ticket = request.args.get('ticket')
        if ticket:
            user, attributes, pgtiou = cas_client.verify_ticket(ticket)
            if user:
                roll = attributes['RollNo']
                email = attributes['E-Mail']
                first_name = attributes['FirstName']
                last_name = attributes['LastName']
                uid = attributes['uid']
                # batch = get_batch(roll)
                cursor = conn.cursor()
                try:
                    cursor.execute( '''
                                    SELECT * FROM Login WHERE Uid = ?
                                    ''', (uid,))
                    entry=cursor.fetchone()
                    conn.commit()
                    if entry:
                        fernet = Fernet(key)
                        token = fernet.encrypt(uid.encode())
                        session['token'] = token
                        return redirect(f'{SUBPATH}/upcomingTravels')
                    else:
                        message='User not found! Please Sign Up.'
                        return render_template('SignUp.html',roll=roll, email=email, first_name=first_name, last_name=last_name, uid=uid, message=message, subpath=SUBPATH)
                except:
                    message='Error with database. Please try again'
                    return render_template('LogIn.html', message=message, subpath=SUBPATH)
            else:
                message='Error with CAS. Please try again'
                return render_template('LogIn.html', message=message, subpath=SUBPATH)
        else:
            message='Error with CAS. Please try again'
            return render_template('LogIn.html', message=message, subpath=SUBPATH)


def get_batch(roll):
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


@app.route(f'{SUBPATH}/Get_userData',methods=['POST', 'GET'])
def Get_userData():
    if request.method == 'POST':
        fname = request.form['fname']
        lname = request.form['lname']
        email = request.form['email']
        roll = request.form['roll']
        uid = request.form['uid']
        batch = get_batch(roll)
        gender = ""

        PhoneNo = request.form['PhoneNo']
        cursor = conn.cursor()
        try:
            cursor.execute('''
                        INSERT INTO Login (Fname, Lname, Email, RollNo, Uid, Batch, Gender, PhoneNo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (fname, lname, email, roll, uid, batch, gender, PhoneNo))
            print('signUp successful')
            conn.commit()
            fernet = Fernet(key)
            token = fernet.encrypt(uid.encode())
            session['token'] = token
            return redirect(f'{SUBPATH}/upcomingTravels')
        except:
            print('Sign Up Failed')
            message='Sign Up Failed!'
            return render_template('LogIn.html', message=message, subpath=SUBPATH)




@app.route(f'{SUBPATH}/getDataForBooking',methods=['POST', 'GET'])
def getForFromCampus():
    if request.method == 'POST':
        token = session['token']
        fernet = Fernet(key)
        uid = fernet.decrypt(token).decode()
        to = request.form['station']
        date = request.form['departureDate']
        time = request.form['departureTime']
        direction = request.form['direction']
        date_time = date + ' ' + time + ':00'
        try:
            cursor = conn.cursor()
            if direction == 'From Campus':
                cursor.execute('''INSERT INTO fromCampus (Uid, DateTime, Station) VALUES (?, ?, ?)''', (uid, date_time, to))
            else:
                cursor.execute('''INSERT INTO toCampus (Uid, DateTime, Station) VALUES (?, ?, ?)''', (uid, date_time, to))
            print('Data inserted')
            conn.commit()
            
        except:
            print('Data not inserted')
        return redirect(f'{SUBPATH}/upcomingTravels')
    else:
        return redirect(f'{SUBPATH}/upcomingTravels')

@app.route(f'{SUBPATH}/deleteBooking', methods=['POST', 'GET'])
def delete_booking_route():
    entry_id = request.form['entry_id']
    direction = request.form['direction']
    try:
        cursor = conn.cursor()
        if direction == 'From Campus':
            cursor.execute('''DELETE FROM fromCampus WHERE BookingID = ?''', (entry_id,))
        else:
            cursor.execute('''DELETE FROM toCampus WHERE BookingID = ?''', (entry_id,))
        conn.commit()
        
        print('Data deleted')
    except:
        print('Data not deleted')
    return redirect(f'{SUBPATH}/upcomingTravels')  

@app.route(f'{SUBPATH}/upcomingTravels')
def upcomingTravels():
    cursor = conn.cursor()
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()
    if(session):
        cur_date_time = datetime.now(local_timezone).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute( '''
                        SELECT * FROM fromCampus WHERE Uid = ?
                        ''', (uid,))
        entries = cursor.fetchall()
        sort_by_datetime(entries)
        fromCampus_entries = []
        for item in entries:
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            station = item[3]
            entry_id = item[0]
            temp_tuple = (date,time,station,entry_id)
            if (date + ' ' + time) < cur_date_time:
                continue
            fromCampus_entries.append(temp_tuple)
        cursor.execute( '''
                        SELECT * FROM toCampus WHERE Uid = ?
                        ''', (uid,))
        
        entries = cursor.fetchall()
        sort_by_datetime(entries)
        toCampus_entries = []
        for item in entries:
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            station = item[3]
            entry_id = item[0]
            temp_tuple = (date,time,station,entry_id)
            if (date + ' ' + time) < cur_date_time:
                continue
            toCampus_entries.append(temp_tuple)
        cursor.execute( '''select * from Login where Uid = ?''', (uid,))
        user = cursor.fetchone()
        return render_template('upcomingtravels.html', fromCampus_entries = fromCampus_entries, toCampus_entries = toCampus_entries, fname=user[0], lname=user[1], subpath=SUBPATH)
    else:
        return redirect(f'{SUBPATH}/')
    
@app.route(f'{SUBPATH}/addnewpage')
def addnewpage():
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Login WHERE Uid = ?', (uid,))
    user = cursor.fetchone()
    return render_template('addnewpage.html', fname=user[0], lname=user[1], subpath=SUBPATH)


@app.route(f'{SUBPATH}/logout_user', methods=['POST', 'GET'])
def logout_user():
    session.pop('token', None)
    return redirect(f'{SUBPATH}/')


@app.route(f'{SUBPATH}/viewBookingRedirect', methods=['POST', 'GET'])
def view_booking_redirect():
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()

    destination_list = []
    starting_list = []
    Batch_list = []
    cur_date_time = datetime.now(local_timezone).strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor = conn.cursor()
        BookingEntries = []
        cursor.execute('''SELECT * FROM fromCampus''')
        entries1 = cursor.fetchall()
        for item in entries1:
            if item[1] == uid:
                continue
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            cursor.execute( '''select * from Login where Uid = ?''', (item[1],))
            data = cursor.fetchone()
            Fname = data[0]
            Lname = data[1]
            Name = Fname + ' ' + Lname
            email_id=data[2]
            Gender = data[6]
            PhoneNo = data[7]
            Batch = data[5]
            station= item[3]
            from_location="IIIT Campus"
            temp_tuple = (date, time, uid, Name, Gender, Batch, station, from_location, email_id, PhoneNo)
            
            if (date + ' ' + time) < cur_date_time:
                continue

            if station not in destination_list:
                destination_list.append(station)

            if "IIIT Campus" not in starting_list:
                starting_list.append("IIIT Campus")

            if Batch not in Batch_list:
                Batch_list.append(Batch)
            BookingEntries.append(temp_tuple)
        
        cursor.execute('''SELECT * FROM toCampus''')
        entries1 = cursor.fetchall()
        for item in entries1:
            if item[1] == uid:
                continue
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            cursor.execute( '''select * from Login where Uid = ?''', (item[1],))
            data = cursor.fetchone()
            Fname = data[0]
            Lname = data[1]
            Name = Fname + ' ' + Lname
            Gender = data[6]
            PhoneNo = data[7]
            Batch = data[5]
            email_id=data[2]
            station= "IIIT Campus"
            from_location=item[3]
            temp_tuple = (date, time, uid, Name, Gender, Batch,station,from_location, email_id, PhoneNo)

            if (date + ' ' + time) < cur_date_time:
                continue

            if from_location not in starting_list:
                starting_list.append(from_location)

            if "IIIT Campus" not in destination_list:
                destination_list.append("IIIT Campus")

            if Batch not in Batch_list:
                Batch_list.append(Batch)

            BookingEntries.append(temp_tuple)
        cursor.execute('SELECT * FROM Login WHERE Uid = ?', (uid,))
        user = cursor.fetchone()
        conn.commit()
        
    except Exception as e:
        print('An error occurred:', e)

    Batch_list.sort()
    destination_list.sort()
    starting_list.sort()
    time_list = ["00:00-01:00", "01:00-02:00", "02:00-03:00", "03:00-04:00", "04:00-05:00", "05:00-06:00", "06:00-07:00", "07:00-08:00", "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "17:00-18:00", "18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00", "22:00-23:00", "23:00-00:00"]
    BookingEntries.sort()
    return render_template('/bookingspage.html', available_options = BookingEntries, fname=user[0], lname=user[1], destination_list=destination_list, starting_list=starting_list, Batch_list=Batch_list, time_list= time_list,subpath=SUBPATH)

def isTimeNotInRange(requested_time, entry_time):
    for i in range(len(requested_time)):
        hour = int(entry_time.split(':')[0])
        timeRange = requested_time[i].split('-')
        timeRange[0] = int(timeRange[0].split(':')[0])
        timeRange[1] = int(timeRange[1].split(':')[0])
        if (hour >= timeRange[0] and hour < timeRange[1]):
            return False
        
        if (hour>=timeRange[0] and timeRange[1] == 0):
            return False
    return True

@app.route(f'{SUBPATH}/apply_filters', methods=['POST'])
def apply_filters():
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()
    
    try:
        cursor = conn.cursor()
        filters = request.json
        cur_date_time = datetime.now(local_timezone).strftime('%Y-%m-%d %H:%M:%S')
        requested_batch = filters.get('selectedBatch').split(",")
        requested_time = filters.get('selectedTime').split(",")
        requested_desti = filters.get('selectedDestination').split(",")
        requested_start = filters.get('selectedStart').split(",")
        requested_date = filters.get('selectedDate')
        
        AllEntries = []
        cursor.execute('''SELECT * FROM fromCampus''')
        entries1 = cursor.fetchall()
        for item in entries1:
            if item[1] == uid:
                continue
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            cursor.execute( '''select * from Login where Uid = ?''', (item[1],))
            data = cursor.fetchone()
            Fname = data[0]
            Lname = data[1]
            Name = Fname + ' ' + Lname
            email_id=data[2]
            Gender = data[6]
            PhoneNo = data[7]
            Batch = data[5]
            station= item[3]
            from_location="IIIT Campus"
            temp_tuple = (date, time, uid, Name, Gender, Batch, station, from_location, email_id, PhoneNo)
            if (date + ' ' + time) < cur_date_time:
                continue
            AllEntries.append(temp_tuple)
        
        cursor.execute('''SELECT * FROM toCampus''')
        entries1 = cursor.fetchall()
        for item in entries1:
            if item[1] == uid:
                continue
            date = item[2].split(' ')[0]
            time = item[2].split(' ')[1]
            cursor.execute( '''select * from Login where Uid = ?''', (item[1],))
            data = cursor.fetchone()
            Fname = data[0]
            Lname = data[1]
            Name = Fname + ' ' + Lname
            Gender = data[6]
            PhoneNo = data[7]
            Batch = data[5]
            email_id=data[2]
            station= "IIIT Campus"
            from_location=item[3]
            temp_tuple = (date, time, uid, Name, Gender, Batch,station,from_location, email_id, PhoneNo)
            if (date + ' ' + time) < cur_date_time:
                continue
            AllEntries.append(temp_tuple)

        BookingEntries = []       
        for entry in  AllEntries:
            if (requested_batch[0] != '' and entry[5] not in requested_batch):
                continue
            if (requested_desti[0] != '' and entry[6] not in requested_desti):
                continue
            if (requested_start[0] != '' and entry[7] not in requested_start):
                continue
            if (requested_date != None and entry[0] != requested_date):
                continue
            if (requested_time[0] != '' and isTimeNotInRange(requested_time, entry[1])):
                continue
            BookingEntries.append(entry)
                
        BookingEntries.sort()
        filtered_data = {'available_options': BookingEntries}
        
        return jsonify(filtered_data)
    
    except Exception as e:
        print("Error:", e)
        return jsonify({'error': str(e)}), 500
    
    

@app.route(f'{SUBPATH}/about')
def about():
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()

    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Login WHERE Uid = ?', (uid,))
    user = cursor.fetchone()

    return render_template('about.html', fname=user[0], lname=user[1], subpath=SUBPATH)


@app.route(f'{SUBPATH}/editprofilepage')
def editprofilepage():
    token = session['token']
    fernet = Fernet(key)
    uid = fernet.decrypt(token).decode()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Login WHERE Uid = ?', (uid,))
        user = cursor.fetchone()
        
        return render_template('editprofilepage.html', fname=user[0], lname=user[1],user=user, subpath=SUBPATH)
    except Exception as e:
        print('An error occurred:2', e)
    


@app.route(f'{SUBPATH}/update_userData', methods=['POST'])
def update_userData():
    try:
        PhoneNo = request.form.get('PhoneNo')
        token = session['token']
        fernet = Fernet(key)
        uid = fernet.decrypt(token).decode()

        cursor = conn.cursor()

        cursor.execute('''
        UPDATE Login
        SET PhoneNo = ?
        WHERE Uid = ?
        ''', (PhoneNo, uid))
        
        conn.commit()
        return redirect(url_for('editprofilepage', update_message='success', subpath=SUBPATH))
        
    except Exception as e:
        print('An error occurred:', e)
        return redirect(url_for('editprofilepage', update_message='error', subpath=SUBPATH))

@app.route(f'{SUBPATH}/static/<path:path>')
def send_report(path: str = ""):
    return send_from_directory('static', path)

if __name__ == '__main__':
    app.run(debug=True)