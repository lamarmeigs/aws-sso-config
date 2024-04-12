# aws-sso-config

When accessing AWS via SSO, a user must have modified their `~/.aws/config` file to include all
account/permission set pairs before invoking any local tools (such as the
[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/),
[Terraform](https://www.terraform.io/), or
[language-specific SDKs](https://aws.amazon.com/developer/tools/)). This is typically done by
invoking `aws configure sso` for each pair.

For convenience, this repository provides a script to automate this configuration. Each profile
will adhere to the naming pattern: `<namespace>-<account-name>-<permission-set-name>` (lowercased
and hyphenated).

## Prerequisites
The script requires Python >=3.8 and the [`boto3`](https://pypi.org/project/boto3/) package.
This may be managed manually:

```shell
$ pyenv use 3.12  # or latest
$ pyenv install 3.12 && pyenv local 3.12
$ pip install boto3
$ ./configure.py --help
```

Or via pipenv:
```shell
$ pipenv sync
$ pipenv run ./configure.py --help
```

## Usage

### Default

Simply running the script with the appropriate AWS access portal will generate profiles for all
account/permission-set pairs accessible through that portal, using the `sso` namespace and the
`us-east-1` region.

```shell
$ ./configure.py https://d-1234567890.awsapps.com/start
$ aws configure list-profiles | grep sso
sso-sandbox-admin
sso-sandbox-read-only
```

### Options

<dl>
  <dt>-n NAMESPACE, --namespace=NAMESPACE</dt>
  <dd>Prefix to add to each profile (default: `sso`)</dd>

  <dt>-r REGION, --region=REGION</dt>
  <dd>AWS region for which to configure profiles (default: `us-east-1`)</dd>

  <dt>-c CONFIG, --config=CONFIG</dt>
  <dd>Path to AWS config file (default: `~/.aws/config`)</dd>
</dt>

### Helpful tips

#### Review available profiles

```shell
$ aws configure list-profiles  # Names only
$ cat ~/.aws/config            # All profile information
```

#### Login

```shell
$ export AWS_PROFILE=<PROFILE-NAME>
$ aws sso login                      # Needed only once per SSO session
$ aws sts get-caller-identity        # Example command
```

#### Other tools

Not all tools respect the `AWS_PROFILE` environment variable by default. Be sure to set
`AWS_SDK_LOAD_CONFIG` to a truthy value (preferably in a `~/.zshrc`, `~/.zprofile`, or equivalent
file).

```shell
export AWS_SDK_LOAD_CONFIG=true
```
