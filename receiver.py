import socket
import datetime

import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# Установка параметров подключения
HOST = config.get('asterisk', 'ip')
PORT = 5038  # Порт для подключения к AMI серверу

# Данные для авторизации на сервере AMI
USERNAME = config.get('asterisk', 'username')
SECRET = config.get('asterisk', 'secret')

# Определение названия файлов сегодняшней даты
today = datetime.datetime.now().strftime('%Y-%m-%d')
full_log_filename = f'{today}_full.log'
# calls_log_filename = f'{today}_calls.log'

# Создание TCP-соединения и открытие файлов для записи
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
full_log_file = open(full_log_filename, 'a')
# calls_log_file = open(calls_log_filename, 'a')

# Авторизация на сервере AMI
login_command = f'Action: login\r\nUsername: {USERNAME}\r\nSecret: {SECRET}\r\n\r\n'
s.sendall(login_command.encode('utf-8'))

# Подписка на события
subscribe_command = 'Action: Filter\r\nFilter: EventList: *\r\n\r\n'
s.sendall(subscribe_command.encode('utf-8'))

# Бесконечный цикл чтения и записи ответов в файл и вывода их в консоль
while True:
    response = s.recv(1024)
    if not response:
        break
    response_text = response.decode('utf-8', 'ignore')
    # print(response_text, end='')
    full_log_file.write(response_text)
    full_log_file.flush()

# Закрытие соединения и файлов
s.close()
full_log_file.close()