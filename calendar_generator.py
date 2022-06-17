import matplotlib
matplotlib.use('AGG')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
import os
import io
import json
import dateparser
import logging
import base64
# for plotting the schedules
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
import numpy as np
# stuff for google calendar api
from os import path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build

# PERMISSIONS FOR API ACCESS
SCOPES = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar']
colors=['pink', 'lightgreen', 'lightblue', 'wheat', 'salmon', 'thistle', 'yellowgreen', 'azure', 'khaki', 'maroon']    
tz = timezone(timedelta(hours=8))
ROOMS = ['L1 Ops Hub', 'L1 Mercury\nPlanning Room', 'L2 Venus\nPlanning Room', 'L3 Terra\nPlanning Room', 'TRACKED VEHICLE\nMOVEMENT', 'Fortitude', 'Spark', 'Steadfast', 'Gearbox', 'Forward Laager']

logger = logging.getLogger(__name__)

def get_event_list(calendarIds: list, start: datetime, end: datetime) -> list:
    service = get_calendar_service()
    event_list = []
    for i,calendarId in enumerate(calendarIds, start=1):
        page_token = None
        while True:
            events = service.events().list(
                calendarId=calendarId,
                pageToken=page_token,
                timeMin=start.isoformat(),
                timeMax = end.isoformat(),
                orderBy='startTime',
                singleEvents=True,
            ).execute()
            for event in events['items']:
                event_list.append({
                    'summary':event['summary'],
                    'start':event['start'],
                    'end':event['end'],
                    'id':event['id'],
                    'room':i,
                })
            page_token = events.get('nextPageToken')
            if not page_token:
                break
    return event_list

def init_testing_local():
    with open('key64.txt','r') as keyfile:
        keys_64 = keyfile.read()
        keys = base64.b64decode(keys_64).decode()
        data = json.loads(keys)
        for k in data.keys():
            dk = data[k]
            if(type(dk) is not str):
                dk = json.dumps(dk)
            os.environ[k]=dk
    return

def get_calendar_service():
    creds = None
    '''
    if path.exists("token.txt"):
        creds = pickle.load(open("token.txt", "rb"))
    # IF IT EXPIRED, WE REFRESH THE CREDENTIALS
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = get_crendetials_google()
    '''
    # key_file_location = 'msvskey.json'
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]), scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)

    return service

def createImageDay(day:datetime):
    booking_date = day.strftime('%d/%m/%Y')
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    daystart_dt = day.astimezone(tz)
    dayend_dt = (day+timedelta(days=1)).astimezone(tz)
    event_list = get_event_list(cal_ids, daystart_dt, dayend_dt)
    
    plt.figure(figsize=(10, 4))
    # non days are grayed
    ax = plt.gca().axes
        
    ax.tick_params(axis='both', which='major', labelsize=8)
    ax.tick_params(axis='both', which='minor', length=0)
    for e in event_list:
        event=e['summary']
        room=e['room']-1
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz)
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz)
        start=start_t.hour+start_t.minute/60
        end=end_t.hour+end_t.minute/60
        if(end<7 or start>18):
            continue
        # plot event
        ax.add_patch(Rectangle((end, room), width=(start-end), height=1, color=colors[room], alpha=1, ec='k',lw=0.7))
        #plot name of booking
        plt.text((start+end)/2, room+0.5, f'''{event}''', va='center', ha='center', fontsize=5)
        # plot beginning time
        plt.text(start+0.02, room+0.95, f'''{start_t.strftime('%H:%M')}''', va='top', fontsize=4)
        #plot end time
        plt.text(end-0.02, room+0.05, f'''{end_t.strftime('%H:%M')}''', va='bottom', ha='right', fontsize=4)

    plt.xticks(np.arange(7,19), [f'{n:02}:00' for n in np.arange(7,19)])
    ax.set_xticks(np.arange(7,19,0.25), minor=True)
    plt.yticks(np.arange(0,5)+.5, ROOMS)
    plt.grid(axis='x', alpha=0.5, which='minor')
    plt.grid(axis='x', alpha=0.5, which='major', lw=1.2)
    plt.ylim(0, 5)
    plt.xlim(7.5, 18.5)

    plt.title(booking_date)
    for y in range(1,5):
        plt.axhline(y=y, color='k', lw=1) 
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return buf

def createImageWeek(facility:int):
    weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday']
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    now = datetime.now()
    monday = now - timedelta(days = now.weekday())
    monday = datetime.combine(monday.date(), datetime.min.time(), tzinfo=tz)
    weekstart_dt = monday.astimezone(tz)
    weekend_dt = (monday+timedelta(days=5)).astimezone(tz)
    event_list = get_event_list([cal_ids[facility]], weekstart_dt, weekend_dt)
    plt.figure(figsize=(10, 4))
    # non days are grayed
    ax = plt.gca().axes
        
    ax.tick_params(axis='both', which='major', labelsize=8)
    ax.tick_params(axis='both', which='minor', length=0)
    for e in event_list:
        event=e['summary']
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz)
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz)
        day = start_t.date().weekday()
        start=start_t.hour+start_t.minute/60
        end=end_t.hour+end_t.minute/60
        if(end<7 or start>18):
            continue
        # plot event
        ax.add_patch(Rectangle((end, day), width=(start-end), height=1, color=colors[day-1], alpha=1, ec='k',lw=0.7))
        #plot name of booking
        plt.text((start+end)/2, day+0.5, f'''{event}''', va='center', ha='center', fontsize=5)
        # plot beginning time
        plt.text(start+0.02, day+0.05, f'''{start_t.strftime('%H:%M')}''', va='top', fontsize=4)
        #plot end time
        plt.text(end-0.02, day+0.95, f'''{end_t.strftime('%H:%M')}''', va='bottom', ha='right', fontsize=4)

    plt.xticks(np.arange(7,19), [f'{n:02}:00' for n in np.arange(7,19)])
    ax.set_xticks(np.arange(7,19,0.25), minor=True)
    plt.yticks(np.arange(0,5)+.5, weekdays)
    plt.grid(axis='x', alpha=0.5, which='minor')
    plt.grid(axis='x', alpha=0.5, which='major', lw=1.2)
    plt.ylim(0, 5)
    plt.xlim(7.5, 18.5)
    plt.gca().invert_yaxis()
    
    plt.title(ROOMS[facility].replace('\n',' '))
    for y in range(1,5):
        plt.axhline(y=y, color='k', lw=1) 
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return buf

def createImageAll(now=None):
    
    weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday']
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    if now is None:
        now = datetime.now()
    monday = now - timedelta(days = now.weekday())
    monday = datetime.combine(monday.date(), datetime.min.time(), tzinfo=tz)
    weekstart_dt = monday.astimezone(tz)
    weekend_dt = (monday+timedelta(days=5)).astimezone(tz)
    event_list = get_event_list(cal_ids, weekstart_dt, weekend_dt)
    plt.figure(figsize=(12, 14))
    # non days are grayed
    ax = plt.gca().axes
        
    ax.tick_params(axis='both', which='major', labelsize=8)
    ax.tick_params(axis='both', which='minor', length=0)
    for e in event_list:
        event=e['summary']
        room=e['room']-1
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz)
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz)
        day = start_t.date().weekday()
        start=start_t.hour+start_t.minute/60
        end=end_t.hour+end_t.minute/60
        if(end<7 or start>18):
            continue
        # plot event
        ax.add_patch(Rectangle((end, (day+((room)/10))), width=(start-end), height=0.2, color=colors[room], alpha=1, ec='k',lw=0.7))
        #plot name of booking
        plt.text((start+end)/2, (day+((room)/10))+0.1, f'''{event}''', va='center', ha='center', fontsize=5)
        # plot beginning time
        plt.text(start+0.01, (day+((room)/10))+0.01, f'''{start_t.strftime('%H:%M')}''', va='top', fontsize=4)
        #plot end time
        plt.text(end-0.01, (day+((room)/10))+0.19, f'''{end_t.strftime('%H:%M')}''', va='bottom', ha='right', fontsize=4)

    plt.xticks(np.arange(7,19), [f'{n:02}:00' for n in np.arange(7,19)])
    ax.set_xticks(np.arange(7,19,0.25), minor=True)
    plt.yticks(np.arange(0,5)+.5, weekdays)
    plt.grid(axis='x', alpha=0.5, which='minor')
    plt.grid(axis='x', alpha=0.5, which='major', lw=1.2)
    plt.ylim(0, 5)
    plt.xlim(7.5, 18.5)
    plt.gca().invert_yaxis()

    for y in range(1,5):
        plt.axhline(y=y, color='k', lw=1) 
    legend_handles = [mpatches.Patch(color=colors[i], label=ROOMS[i]) for i in range(len(ROOMS))]
    ax.legend(handles=legend_handles, 
        prop={'size': 5},
        bbox_to_anchor=(0., 1.02, 1., .102), 
        loc='upper left',
        ncol=5, mode="expand", 
        borderaxespad=0.
    )
    plt.title(f'''All bookings, week of {monday.strftime('%d/%m/%Y')}''')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return buf

def generate_keys64():
    return (base64.b64encode(json.dumps(json.load(open('keys.json','r'))).encode()))

# TESTING FUNCTION, IGNORE
def main() -> None:
    '''init_testing_local()
    today = datetime.combine(datetime.now().date(), datetime.min.time(), tzinfo=tz)'''
    
    k64 = generate_keys64()
    with open('key64.txt','wb') as outfile:
        outfile.write(k64)
        print(k64)
    return

if __name__ == '__main__':
    main()