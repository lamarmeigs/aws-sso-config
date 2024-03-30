#!/usr/bin/env python3
"""
Configure the AWS CLI with the current user's SSO profiles.

To use the AWS CLI in accounts accessed via SSO, a user must either invoke
``aws configure sso`` for each account-role pair OR manually edit their
``~/.aws/config`` file. This tool automates the latter, creating/updating all
of the user's access in a single call.

For instance, if the user can access a "Sandbox" account (#123456789011) with
an "Admin" role, it will generate the following profile:

    [profile sso-sandbox-admin]
    sso_start_url = https://ORGANIZATION.awsapps.com/start
    sso_account_id = 123456789011
    sso_role_name = Admin
    sso_region = us-east-1
    region = us-east-1

Which can then be used with the following commands:

    $ export AWS_PROFILE=sso-sandbox-admin
    $ aws sso login
    $ aws sts get-caller-identity

Note that the ``~/.aws/config` file will be backed up in case of error. Backups
should be manually removed.
"""
import configparser
import json
import os
import re
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

try:
    import boto3
except ImportError:
    print('Please install boto3:\n\t$ pip install boto3')
    exit(1)


ACCESS_PORTAL_URL = 'https://ORGANIZATION.awsapps.com/start'
AWS_CONFIG_PATH = os.environ.get('AWS_CONFIG_FILE', '.aws/config')
AWS_SSO_CACHE_PATH = '.aws/sso/cache'
CLIENT_NAME = 'profile_manager'
PROFILE_PREFIX = 'grow'
REGION = 'us-east-1'


def configure_profiles(config_path: str = AWS_CONFIG_PATH):
    """Configure the AWS CLI with the current user's SSO profiles."""
    parent_directory_path, config_file = os.path.split(config_path)
    parent_directory = Path.home().joinpath(parent_directory_path)
    parent_directory.mkdir(exist_ok=True, parents=True)

    print(f'Reading {config_file}...')
    aws_config_path = parent_directory.joinpath(config_file)
    aws_config = configparser.ConfigParser()
    try:
        with aws_config_path.open() as f:
            aws_config.read_file(f)
    except FileNotFoundError:
        pass
    else:
        print('Backing up configuration...')
        with aws_config_path.with_suffix('.bak').open('w') as backup:
            aws_config.write(backup)

    print('Logging into AWS...')
    token = login()

    print('Retrieving accessible accounts and roles...')
    current_profiles = generate_profiles(token)
    for profile_name, profile_config in current_profiles.items():
        aws_config[profile_name] = profile_config

    print('Removing outdated profiles...')
    all_sso_profiles = {
        section
        for section in aws_config.sections()
        if section.startswith(f'profile {PROFILE_PREFIX}')
    }
    outdated_profiles = all_sso_profiles - current_profiles.keys()
    for profile_name in outdated_profiles:
        del aws_config[profile_name]

    print(f'Updating {config_file}...')
    with aws_config_path.open('w') as f:
        aws_config.write(f)

    print('Done!')


def login(access_portal_url: str = ACCESS_PORTAL_URL) -> str:
    """Generate an access token using the AWS access portal's IdP.

    Register the current device with IAM Identity Center (aka AWS SSO), then
    open a browser for the user to authorize access. The resulting access token
    can be used for subsequent ``sso`` commands. It will be cached for reuse.
    """
    cache = Path.home().joinpath(AWS_SSO_CACHE_PATH)
    cache.mkdir(exist_ok=True, parents=True)
    cached_token_path = cache.joinpath(f'{CLIENT_NAME}.json')
    if (token := _get_cached_token(cached_token_path)) is not None:
        return token

    oidc = boto3.client('sso-oidc', region_name=REGION)
    client_credentials = oidc.register_client(
        clientName=CLIENT_NAME,
        clientType='public',
    )

    device_authorization = oidc.start_device_authorization(
        clientId=client_credentials['clientId'],
        clientSecret=client_credentials['clientSecret'],
        startUrl=access_portal_url,
    )

    webbrowser.open(device_authorization['verificationUriComplete'])

    while True:
        try:
            token_response = oidc.create_token(
                clientId=client_credentials['clientId'],
                clientSecret=client_credentials['clientSecret'],
                grantType='urn:ietf:params:oauth:grant-type:device_code',
                deviceCode=device_authorization['deviceCode'],
            )
        except oidc.exceptions.AuthorizationPendingException:
            time.sleep(1)
        else:
            break

    token = token_response['accessToken']
    _cache_token(cached_token_path, token, token_response['expiresIn'])
    return token


def _get_cached_token(cache: Path) -> Optional[str]:
    try:
        with cache.open() as f:
            cached_token = json.load(f)
        assert cached_token['expires'] > datetime.now().timestamp()
    except (AssertionError, FileNotFoundError):
        return None
    else:
        return cached_token['token']


def _cache_token(cache: Path, token: str, expires_in: int):
    expiration = datetime.now() + timedelta(seconds=expires_in)
    to_cache = {'expires': expiration.timestamp(), 'token': token}
    with cache.open('w') as f:
        json.dump(to_cache, f)


def generate_profiles(
    token: str,
    access_portal: str = ACCESS_PORTAL_URL,
) -> Dict[str, Dict[str, str]]:
    """Retrieve all AWS accounts the user can access, with their roles.

    The resulting dictionary will be config-ready: it maps a generated profile
    name to that profile's expected key-value pairs. For more information, see
    the AWS documentation:

        https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
    """
    profiles = {}
    sso_client = boto3.client('sso', region_name=REGION)
    paginator = sso_client.get_paginator('list_accounts')
    for account in paginator.paginate(accessToken=token).search('accountList'):
        account_id = account['accountId']
        account_name = account['accountName']

        account_roles = sso_client.list_account_roles(
            accessToken=token,
            accountId=account_id,
        )
        for role in account_roles.get('roleList', []):
            role_name = role['roleName']

            profile_name = _name_profile(account_name, role_name)
            profiles[f'profile {profile_name}'] = {
                'sso_start_url': access_portal,
                'sso_account_id': account_id,
                'sso_role_name': role_name,
                'sso_region': REGION,
                'region': REGION,
            }
    return profiles


def _name_profile(account_name: str, role_name: str) -> str:
    """Generate a name for a profile.

    Results will be a lowercased, hyphenated combination of a common prefix,
    the account name, and the role name.

    Example:
        >>> _name_profile('MyAccount', 'Admin')
        'sso-my-account-admin'
    """

    def _hyphenate(word: str) -> str:
        # Shamelessly adapted from https://github.com/jpvanhal/inflection
        word = re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1-\2', word)
        word = re.sub(r"([a-z\d])([A-Z])", r'\1-\2', word)
        return word.lower()

    return '-'.join(
        [PROFILE_PREFIX, _hyphenate(account_name), _hyphenate(role_name)]
    )


if __name__ == '__main__':
    configure_profiles()
