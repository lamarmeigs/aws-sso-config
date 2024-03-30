from datetime import datetime, timedelta
import json
import time
import webbrowser
from pathlib import Path

import boto3

cache = Path.home().joinpath(".aws/sso/cache")
cache.mkdir(exist_ok=True, parents=True)

oidc = boto3.client('sso-oidc')


def sso_login(start_url):
    cached_token_path = cache.joinpath('profile_manager_token.json')
    try:
        with cached_token_path.open() as f:
            cached_token = json.load(f)
            if cached_token['expires'] > datetime.now().timestamp():
                return cached_token['token']
    except FileNotFoundError:
        pass

    client_response = oidc.register_client(
        clientName='profile_manager',
        clientType='public',
    )

    auth_response = oidc.start_device_authorization(
        clientId=client_response['clientId'],
        clientSecret=client_response['clientSecret'],
        startUrl=start_url,
    )

    webbrowser.open(auth_response["verificationUriComplete"])

    while True:
        try:
            token_response = oidc.create_token(
                clientId=client_response['clientId'],
                clientSecret=client_response['clientSecret'],
                grantType='urn:ietf:params:oauth:grant-type:device_code',
                deviceCode=auth_response['deviceCode'],
            )
            expires = datetime.now() + timedelta(seconds=token_response['expiresIn'])
            with cached_token_path.open('w') as f:
                to_cache = {
                    'expires': expires.timestamp(),
                    'token': token_response['accessToken']
                }
                json.dump(to_cache, f)

            return token_response['accessToken']
        except oidc.exceptions.AuthorizationPendingException:
            time.sleep(1)
