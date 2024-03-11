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
    start = 0
    bitrix_users = {}

    while True:
        response = requests.post(f'{BITRIX_URL}user.get', data={'ACTIVE': 'true', 'start': start}).json()
        if 'result' in response:
            users = response['result']
            for user in users:
                if user.get('UF_PHONE_INNER'):
                    bitrix_users[user.get('UF_PHONE_INNER')] = user.get('ID')
            start += len(users)
            if 'next' not in response:
                break
        else:
            print('Ошибка при получении списка пользователей', response)
            break

    with open(BITRIX_USERS_FILE, 'w') as file:
        json.dump(bitrix_users, file)


def get_user_id(internal_number):
    # Загружаем или обновляем данные пользователей
    for _ in range(2):
        try:
            with open(BITRIX_USERS_FILE, 'r') as file:
                bitrix_users = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            bitrix_users = {}

        # Проверяем, предоставлен ли номер и есть ли он в bitrix_users
        if internal_number and str(internal_number) in bitrix_users:
            return bitrix_users[str(internal_number)], False

        # Обновляем файл только если пользователь не найден в первой итерации
        update_bitrix_users_file()

    # Возвращаем значение по умолчанию, если internal_number None или пользователь не найден
    default_value = DEFAULT_USER_ID if DEFAULT_USER_ID else next(iter(bitrix_users.values()), None)
    return default_value, True


# Регистрация звонка в Битрикс24
def register_call(bitrix_user_id, phone_number, call_type):
    register_param = {
        'USER_ID': bitrix_user_id,
        'PHONE_NUMBER': phone_number,
        'TYPE': call_type,
        'SHOW': SHOW_CARD,
        'CRM_CREATE': CRM_CREATE
    }

    call_data = requests.post(f'{BITRIX_URL}telephony.externalcall.register', register_param).json()
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


def card_action(call_id, user_id, action):
    if SHOW_CARD == 1:
        call_data = {
            'CALL_ID': call_id,
            'USER_ID': user_id
        }

        requests.post(f'{BITRIX_URL}telephony.externalcall.{action}', call_data).json()