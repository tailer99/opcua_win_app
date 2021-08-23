
from linebot import LineBotApi
from linebot.models import TextSendMessage
from linebot.exceptions import LineBotApiError


# def init_line_message():
gv_line_access_token = '8WdMl+6BSZCrABdh3X8qsdOvqUWb+u+LlwIJb47WUot/sdf12Ne3Kj/+m5CLdshoXEp5iJ03X0oXjfusIWWtKxoFR3NhFY7WV6YzT41y+CIPLbpM7Iss0mrNY/GiQ8wZR+flkVYc9sRLACLwYJvpFgdB04t89/1O/w1cDnyilFU='

print('when started : ')
line_bot_api = LineBotApi(gv_line_access_token)
print(line_bot_api)

def send_line_message(to_id, textmsg):
    try:
        # a = line_bot_api.push_message('U0c5a0782c992f3f5787bfc8786742857', TextSendMessage(text='Hello World!'))
        a = line_bot_api.push_message(to_id, TextSendMessage(text=textmsg))
        print('check : ', a)

    except LineBotApiError as e:
        print(e)
