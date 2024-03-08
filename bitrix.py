import os
import json
import time
import requests
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# Подключение к битрикс
BITRIX_URL = config.get('bitrix', 'url')
CRM_CREATE = config.get('bitrix', 'crm_create')
SHOW_CARD = config.get('bitrix', 'show_card')
DEFAULT_USER_ID = config.get('bitrix', 'default_user_id')

# Путь к файлу с пользователями Битрикс
BITRIX_USERS_FILE = 'bitrix_users.json'

def update_bitrix_users_file():
    user_data = requests.post(f'{BITRIX_URL}user.get', {'ACTIVE': 'true'}).json()
    if 'result' in user_data:
        all_users = user_data['result']
        bitrix_users = {user['UF_PHONE_INNER']: user['ID'] for user in all_users}
        with open(BITRIX_USERS_FILE, 'w') as file:
            json.dump(bitrix_users, file)
    else:
        print('Ошибка при получении списка пользователей', user_data)


def get_user_id(internal_number):
    # Проверка и инициализация файла с пользователями
    if not os.path.exists(BITRIX_USERS_FILE) or os.path.getsize(BITRIX_USERS_FILE) == 0:
        update_bitrix_users_file()

    bitrix_users = {}

    # Попытка поиска пользователя до двух раз: до и после обновления файла
    for _ in range(2):
        with open(BITRIX_USERS_FILE, 'r') as file:
            bitrix_users = json.load(file)

        if internal_number is None:
            return globals().get('DEFAULT_USER_ID', next(iter(bitrix_users.values()), None))

        if str(internal_number) in bitrix_users:
            return bitrix_users[str(internal_number)]

        # Обновляем файл только если пользователь не найден в первой итерации
        update_bitrix_users_file()

    # Возвращаем DEFAULT_USER_ID если пользователь не найден после обновления
    return globals().get('DEFAULT_USER_ID', next(iter(bitrix_users.values()), None))


# Регистрация звонка в Битрикс24
def register_call(bitrix_user_id, phone_number, call_type):
    register_param = {
        'USER_ID': bitrix_user_id,
        'PHONE_NUMBER': phone_number,
        'TYPE': call_type,
        'SHOW': SHOW_CARD,
        'CRM_CREATE': CRM_CREATE
    }

    call_data = requests.post(f'{BITRIX_URL}telephony.externalcall.register', 
                              json=register_param).json()
    if 'result' in call_data:
        return call_data['result']['CALL_ID']
    else:
        print('ОШИБКА!!!!! register_call', phone_number, call_data)


def finish_call(call_data):
    finish_param = {
        'CALL_ID': call_data["bitrix_call_id"],
        'USER_ID': call_data["bitrix_user_id"],
        'DURATION': round(time.time() - call_data["start_time"]),
        'STATUS_CODE': call_data["call_status"]
    }

    response = requests.post(f'{BITRIX_URL}telephony.externalcall.finish', finish_param).json()
    if 'result' in response:
        return True
    else:
        print('ОШИБКА finish_call', response)
        return False


def attachRecord(call_data, encoded_file):
    file_data = {
        'CALL_ID': call_data["bitrix_call_id"],
        'FILENAME': call_data["file_name"],
        'FILE_CONTENT': encoded_file
    }

    requests.post(f'{BITRIX_URL}telephony.externalCall.attachRecord', file_data).json()


def show_card(call_id, user_id):
    call_data = {
        'CALL_ID': call_id,
        'USER_ID': user_id
    }

    response = requests.post(f'{BITRIX_URL}telephony.externalcall.show', call_data).json()

    print('WWWWWWWWW', response)