# BitrixAmiSync

Заполнить данные в config.ini

```
[asterisk]
ip = 192.168.1.247
username = bitrixamisync
secret = 

[bitrix]
url = 
```

Передача информации о звонках из Asterisk в Битрикс24 через AMI

### cel_general_custom.conf

```
[general]+
apps=dial
[manager]+
enabled=yes
```

#### AMI менеджер bitrixamisync (read CALL, Cdr, dialplan)

/admin/config.php?display=manager

```
[bitrixamisync]
secret = secret
deny=0.0.0.0/0.0.0.0
permit=127.0.0.1/255.255.255.0
read = call,cdr,dialplan
write = 
writetimeout = 100
```

#### Создать службу bitrixamisync 

```
nano /etc/systemd/system/bitrixamisync.service
```
```
[Unit]
Description=BitrixAmiSync

[Service]
ExecStart=/usr/bin/python3 /home/api/bitrixamisync.py
WorkingDirectory=/home/api/
Restart=always
User=nobody
Group=nobody

[Install]
WantedBy=multi-user.target
```
```
fwconsole restart
sudo systemctl daemon-reload
sudo systemctl start bitrixamisync
sudo systemctl enable bitrixamisync
```
