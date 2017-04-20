import requests
import time
import platform
import os
import subprocess
import xml.dom.minidom
import json
from tkinter import *

# 生成一个会话
session = requests.Session()
'''
url = "https://qq.com"
r = requests.get(url, verify=False) 
'''
# 1. 登录url
url = 'https://login.weixin.qq.com/jslogin'
params = {
    'appid': 'wx782c26e4c19acffb',
    'redirect_uri': 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage',
    'fun': 'new',
    'lang': 'en_US',
    '_': int(time.time()),
    }

response = session.get(url, params=params)

print('Content: %s' % response.text)

regx = r'window.QRLogin.code = (\d+); window.QRLogin.uuid = "(\S+?)";'

data = re.search(regx, response.text)

# 获取UUID
uuid = None
if data and data.group(1) == '200':
    uuid = data.group(2)
    print('uuid: %s' % uuid)

# 拼得获取qrcode的url
url = 'https://login.weixin.qq.com/qrcode/' + uuid

# 继续获取二维码
r = session.get(url, stream=True)

QR_CODE = 'QRCode.jpg'

with open(QR_CODE, 'wb') as f:
    f.write(r.content)
'''
# 等价于：
f = open(QR_CODE, 'wb')  
try:
    data = f.write(r.content)  
finally:  
    f.close()
'''

'''top = Tk()
image = Image.open(QR_CODE)
logo = PhotoImage(image)
label = Label(top, image=logo)
label.pack()
top.mainloop()
'''

# 打开图片
if platform.system() == 'Darwin':
    subprocess.call(['open', QR_CODE])
elif platform.system() == 'Linux':
    subprocess.call(['xdg-open', QR_CODE])
else:
    os.startfile(QR_CODE)

# 使用微信扫描确认登录
while 1:
    url = 'https://login.weixin.qq.com/cgi-bin/mmwebwx-bin/login'
    payload = {
        'tip': 1,
        'uuid': uuid,
        '_': int(time.time()),
    }
    print('qr code scaning:' + str(payload))
    r = session.get(url, params=payload)
    print('qr code scaned ' + r.text)

    regx = r'window.code=(\d+)'
    data = re.search(regx, r.text)


    # 没数据
    if not data:
        print('no data')
        time.sleep(1)
        continue

    status_code = data.group(1)

    if status_code == '200':
        # 获取登录信息做准备
        uriRegex = r'window.redirect_uri="(\S+)";'
        redirectUri = re.search(uriRegex, r.text).group(1)
        print('redirect uri: ' + redirectUri)
        break
    elif status_code == '201':
        print('You have scanned the QRCode, press confirm button on the phone')
        time.sleep(1)
        continue
    elif status_code == '408':
        raise Exception('QRCode should be renewed')


r = session.get(redirectUri, allow_redirects=False)
# response data <xml>
baseRequestText = r.text
# 重定向登录，成功
print('Login successfully')

redirectUri = redirectUri[:redirectUri.rfind('/')]


def get_login_info(s):
    request = {}
    for node in xml.dom.minidom.parseString(s).documentElement.childNodes:
        if node.nodeName == 'skey':
            request['Skey'] = str(node.childNodes[0].data)
        elif node.nodeName == 'wxsid':
            request['Sid'] = str(node.childNodes[0].data)
        elif node.nodeName == 'wxuin':
            request['Uin'] = str(node.childNodes[0].data)
        elif node.nodeName == 'pass_ticket':
            request['DeviceID'] = str(node.childNodes[0].data)
    return request

# 获取登录信息
baseRequest = get_login_info(baseRequestText)

url = '%s/webwxinit?r=%s' % (redirectUri, int(time.time()))
data = {
    'BaseRequest': baseRequest,
}

headers = {'ContentType': 'application/json; charset=UTF-8',
           'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:54.0) Gecko/20100101 Firefox/54.0'}
r = session.post(url, data=json.dumps(data), headers=headers)

user_info = json.loads(r.content.decode('utf-8', 'replace'))

print(user_info)
myname = user_info['User']['NickName']
print(f'Log in as {myname}')

# 后面所有操作都基于

'''获取消息'''
info = {
    'skey': baseRequest['Skey'],
    'sid': baseRequest['Sid'],
    'uin': baseRequest['Uin'],
    'deviceid': baseRequest['DeviceID'],
}

print('-------------------------------\n' + json.dumps(info))


# 获取联系人列表
def get_contact_list(send_base_url, base_request=baseRequest):
    contacts_url = '%s/webwxgetcontact?r=%s&seq=%s&skey=%s' % (send_base_url, int(time.time()*1e4), 0, base_request['Skey'])
    send_headers = {'ContentType': 'application/json; charset=UTF-8'}
    contacts_response = session.get(contacts_url, headers=send_headers)
    json_contacts = json.loads(contacts_response.content.decode('utf-8', 'replace'))
    return json_contacts


contact_list = get_contact_list(send_base_url=redirectUri)['MemberList']
print(contact_list)

'''发送一发消息'''


def send_msg(send_base_url, my_name, message, to_user_name=None, base_request=baseRequest):
    send_url = '%s/webwxsendmsg' % send_base_url
    payloads = {
            'BaseRequest': base_request,
            'Msg': {
                'Type': 1,
                'Content': str(message, 'utf-8'),
                'FromUserName': my_name,
                'ToUserName': (to_user_name if to_user_name else my_name),
                'LocalID': int(time.time()*1e4),
                'ClientMsgId': int(time.time()*1e4),
                },
            }
    print(payloads)
    send_headers = {'ContentType': 'application/json; charset=UTF-8'}
    msg_result = session.post(send_url, data=json.dumps(payloads, ensure_ascii=False).encode(), headers=send_headers)
    print(msg_result.status_code)
    print(msg_result.content)


print('send msg:')
for contact in contact_list:
    if contact['NickName'] == '若鱼':
        ruoyu = contact['UserName']
        break

msg = None
while msg != 'q':
    if msg:
        send_msg(send_base_url=redirectUri, my_name=user_info['User']['UserName'], message=msg, to_user_name=ruoyu)
    msg = input('$: ').encode()

print('end. byebye')



