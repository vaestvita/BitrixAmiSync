#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import asyncio 
import base64
from datetime import datetime
from panoramisk import Manager
import requests, json

import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# данные для доступа к AMI
ip = config.get('asterisk', 'ip')
username =  config.get('asterisk', 'username')
secret = config.get('asterisk', 'secret')

# Количество символов в номере
number_count = int(config.get('asterisk', 'number_count'))

# Подключение к битрикс
bitrix_url = config.get('bitrix', 'url')
register = 'telephony.externalcall.register'
finish = 'telephony.externalcall.finish'
attachRecord = 'telephony.externalCall.attachRecord'

# Поиск пользователя Битрикс24
def find_user_id(internal_number):
    all_users = requests.post(bitrix_url + 'user.get', {'ACTIVE': 'true'}).json()['result']
    for user in all_users:
        if user.get('UF_PHONE_INNER') == internal_number:
            return user['ID']
    return all_users[0]['ID']

# Регистрация звонка в Битрикс24
def register_call(bitrix_user_id, phone_number, call_type):
    register_param = {
        'USER_ID': bitrix_user_id,
        'PHONE_NUMBER': phone_number,
        'TYPE': call_type,
        'SHOW': '0'
    }

    bitrix_call_id = requests.post(bitrix_url + register, register_param).json()['result']['CALL_ID']
    return bitrix_call_id

# Ассоциативный массив 
calls_data = {}

# Подключение AMI
manager = Manager(loop=asyncio.get_event_loop(),
                  host=ip,
                  port=5038,
                  ssl=False,
                  encoding='utf8',
                  username=username,
                  secret=secret)


# Подписка на события Новый вызов
@manager.register_event('Newchannel')
def NewchannelEvent(manager, message):

    # Обработка событий входящего вызова
    if message.Context == 'from-trunk' and message.Exten != 's':
        call_id = message.Linkedid
        calls_data[call_id] =  {"phone_number": message.CallerIDNum, 'bitrix_user_id': None}
        print('Входящий: ', call_id, calls_data[call_id])


    # Обработка событий исходящего вызова
    elif message.Context == 'from-internal' and message.Exten not in ['s', '*8'] and len(message.Exten) >= number_count:
        call_id = message.Linkedid
        phone_number = message.Exten

        if phone_number.startswith('9'):
            phone_number = phone_number[1:]

        bitrix_user_id = find_user_id(message.CallerIDNum)
        bitrix_call_id = register_call(bitrix_user_id, phone_number, 1)
        calls_data[call_id] =  {"phone_number": phone_number, "bitrix_call_id": bitrix_call_id, 'bitrix_user_id': bitrix_user_id}
        print('Исходящий: ', call_id, calls_data[call_id])


# Подписка на событие вызов принят
@manager.register_event('BridgeEnter')
def BridgeEnter(manager, message):
    # Для входящих вызовов
    call_id = message.Linkedid
    if call_id in calls_data:
        if calls_data[call_id]["bitrix_user_id"] is None and message.ChannelStateDesc == 'Up' and message.Context == 'macro-dial-one' and message.CallerIDNum != calls_data[call_id]["phone_number"]:
            calls_data[call_id]["bitrix_user_id"] = find_user_id(message.CallerIDNum)
            calls_data[call_id]["bitrix_call_id"] = register_call(calls_data[call_id]["bitrix_user_id"], calls_data[call_id]["phone_number"], 2)

            print('Оператор ответил: ', call_id, calls_data[call_id])

        # Для исходящих звонков
        elif message.ChannelStateDesc == 'Up' and message.Context == 'macro-dialout-trunk':
            print('Абонент ответил: ', call_id, calls_data[call_id])


# Перехваченный вызов
@manager.register_event('Pickup')
def Pickup(manager, message):
    call_id = message.TargetLinkedid
    if call_id in calls_data:
        calls_data[call_id]["bitrix_user_id"] = find_user_id(message.CallerIDNum)
        calls_data[call_id]["bitrix_call_id"] = register_call(calls_data[call_id]["bitrix_user_id"], calls_data[call_id]["phone_number"], 2)
        print(f'Вызов перехвачен номером {message.CallerIDNum}')


# Событие VarSet (MIXMONITOR_FILENAME)
@manager.register_event('VarSet')
def VarSetEvent(manager, message):
    call_id = message.Linkedid
    if message.Variable == 'MIXMONITOR_FILENAME' and call_id in calls_data:
        calls_data[call_id]["file_patch"] = message.Value
        calls_data[call_id]["file_name"] = os.path.basename(message.Value)

# событие CEL
@manager.register_event('CEL')
def CelEvent(manager, message):
    call_id = message.Linkedid
    if call_id in calls_data:
        if message.EventName == 'CHAN_START' and message.Context == 'from-trunk':
            calls_data[call_id]["start_time"] = datetime.strptime(message.EventTime, '%Y-%m-%d %H:%M:%S')

        if message.EventName == 'HANGUP' and message.Exten == 'h':
            extra = json.loads(message.Extra)
            hangupcause = extra.get('hangupcause')
            dialstatus = extra.get('dialstatus')
            status_dict = {
                'CANCEL': 304,
                'ANSWER': 200,
                'BUSY': 486,
            }
            if hangupcause in [16, 17]:
                calls_data[call_id]["dial_status"] = status_dict.get(dialstatus)
            elif not dialstatus or dialstatus not in status_dict:
                calls_data[call_id]["dial_status"] = 603

        if message.EventName == 'LINKEDID_END':
            call_id = message.Linkedid

            # Если входящий не отвечен        
            if calls_data[call_id]["bitrix_user_id"] is None:
                calls_data[call_id]["bitrix_user_id"] = find_user_id(None)
                calls_data[call_id]["bitrix_call_id"] = register_call(calls_data[call_id]["bitrix_user_id"], calls_data[call_id]["phone_number"], 2)
                calls_data[call_id]["dial_status"] = 304

            if "start_time" not in calls_data[call_id]:
                calls_data[call_id]["duration"] = 10
            else:
                calls_data[call_id]["end_time"] = datetime.strptime(message.EventTime, '%Y-%m-%d %H:%M:%S')
                calls_data[call_id]["duration"] = round((calls_data[call_id]["end_time"] - calls_data[call_id]["start_time"]).total_seconds())

            # Закрытие звонка в битрикс
            finish_param = {
            'CALL_ID': calls_data[call_id]["bitrix_call_id"],
            'USER_ID': calls_data[call_id]["bitrix_user_id"],
            'DURATION': calls_data[call_id]["duration"],
            'STATUS_CODE':calls_data[call_id]["dial_status"]
            }

            response_finish = requests.post(bitrix_url + finish, finish_param)
            print(f"Response from finish: {response_finish.json()}")

            # Отправка файла записи
            if calls_data[call_id]["dial_status"] == 200:
                with open(calls_data[call_id]["file_patch"], "rb") as file:
                    encoded_file = base64.b64encode(file.read())

                file_param = {
                    'CALL_ID': calls_data[call_id]["bitrix_call_id"],
                    'FILENAME': calls_data[call_id]["file_name"],
                    'FILE_CONTENT': encoded_file
                }

                response_attachRecord = requests.post(bitrix_url + attachRecord, file_param)
                print(f"Response from attachRecord: {response_attachRecord.json()}")
        
                # Удаление записи из массива
                del calls_data[call_id]
            else:
                del calls_data[call_id]

def main():
    try:
        manager.connect()
    except Exception as e:
        print(f"Не удалось подключиться к AMI: {e}")
        return

    try:
        manager.loop.run_forever()
    except KeyboardInterrupt:
        manager.loop.close()

if __name__ == '__main__': 
     main()