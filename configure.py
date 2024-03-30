import configparser
from pathlib import Path

import boto3

from sso_login import sso_login


# TODO: Move this to a config file
access_portal_url = 'https://ORGANIZATION.awsapps.com/start'
sso_profile_prefix = "sso"
role_mapping = {
    'Admin': 'admin',
    'Audit': 'audit',
    'ReadOnly': 'read',
}

valid_sso_profiles = set()


aws_config_file = Path.home().joinpath(".aws/config")

# Read AWS Profile Config
aws_config = configparser.ConfigParser()
with aws_config_file.open() as f:
    aws_config.read_file(f)

# Backup Config file
with aws_config_file.with_suffix('.bak').open('w') as wf:
    aws_config.write(wf)

# Iterate through available accounts and roles; add and update profiles
client = boto3.client('sso')
token = sso_login(access_portal_url)
account_paginator = client.get_paginator('list_accounts')
role_paginator = client.get_paginator('list_account_roles')
for account in account_paginator.paginate(accessToken=token).search('accountList'):
    name = account['accountName'].replace(' ', '-').lower()
    account_id = account['accountId']

    for role in role_paginator.paginate(accessToken=token, accountId=account_id).search('roleList'):
        role_name = role_mapping.get(role['roleName'], role['roleName'])
        profile_name = "profile " + "-".join(filter(None, [sso_profile_prefix, name, role_name]))

        valid_sso_profiles.add(profile_name)

        try:
            profile_config = dict(aws_config[profile_name])
        except KeyError:
            profile_config = {}

        profile_config['sso_start_url'] = access_portal_url
        profile_config['sso_account_id'] = role['accountId']
        profile_config['sso_role_name'] = role['roleName']
        profile_config['sso_region'] = 'us-west-2'
        profile_config['region'] = 'us-west-2'

        aws_config[profile_name] = profile_config

# Remove outdated sso- profiles
all_sso_profiles = set(s for s in aws_config.sections() if s.startswith('profile sso'))
invalid = all_sso_profiles - valid_sso_profiles
for profile in invalid:
    del aws_config[profile]

# Write new version of aws profile config
with aws_config_file.open('w') as wf:
    aws_config.write(wf)
