import requests

session = requests.session()


def get_response(response, *args, **kwargs):
    print(response.elapsed)
    print(response.json())

r = requests.get('https://api.github.com', hooks=dict(response=get_response))

def reverse_str( s ):
    t = ''
    for x in range(len(s)-1, -1,-1):
        t += s[x]
    return t

print(reverse_str('hahhax'))

