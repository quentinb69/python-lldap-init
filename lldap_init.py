# Inspired from https://github.com/lldap/lldap/issues/654#issuecomment-1694251863
import subprocess
import json
import os

from requests import JSONDecodeError, RequestException, Session
from qlient.http import HTTPBackend, HTTPClient, Fields

# set structures for graphQL
GROUP_FIELDS = Fields("id", "displayName")
USER_FIELDS = Fields("id", "email", "displayName", groups=GROUP_FIELDS)
# default configuration
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', "/config/admin_password")
CONFIG_FILE = os.environ.get('CONFIG_FILE', "/config/config_file.json")


def validate(expression: bool, message: str = "") -> None:
    """ Validate, to be used like Assert """

    if not expression:
        print(message)
        exit(1)

    return


def validateConfiguration(configuration_file: str, admin_password_file: str) -> json:
    """ Validate and return configuration dict """

    validate(os.path.isfile(admin_password_file) is True, "admin_password_file '" +
             admin_password_file + "' does not exist...")
    validate(os.path.isfile(configuration_file) is True, "config_file '" +
             configuration_file + "' does not exist...")

    with open(configuration_file) as config_file:
        configuration: json = json.load(config_file)
    validate(len(configuration["admin_username"])
             > 0, "admin_username not set...")
    validate(len(configuration["ldap_url"]) > 0, "ldap_url not set...")
    validate(len(configuration["web_url"]) > 0, "web_url not set...")
    validate(len(configuration["base_dn"]) > 0, "base_dn not set...")
    validate(len(configuration["seed"]) > 0, "seed not set...")

    return configuration


def createauthenticatedWebClient(admin_username: str, web_url: str, admin_password_file: str) -> HTTPClient:
    """ Log into LLDAP, and return the HTTPClient to be used for next requests """

    session = Session()
    with open(admin_password_file, "r") as f:
        admin_password = f.read()
    try:
        jwt_token_request = session.post(
            url=f'{web_url}/auth/simple/login',
            json={
                "username": admin_username,
                "password": admin_password,
            }
        )
        admin_password = ""
    except RequestException as e:
        raise SystemExit(e)

    validate(jwt_token_request.status_code == 200, jwt_token_request.content)
    jwt_token = jwt_token_request.json()["token"]

    session.headers["Authorization"] = f"Bearer {jwt_token}"
    httpclient = HTTPClient(HTTPBackend(
        f'{web_url}/api/graphql', session=session))

    return httpclient


def create_single_user(user: json, ldap_url: str, base_dn: str, admin_username: str, admin_password_file: str, client: HTTPClient) -> json:
    """ Create a user via graphql and set its password via ldappasswd """

    groups = user.pop("groups", [])
    password_file = user.pop("password_file")

    # create user
    req = client.mutation.createUser(user=user, _fields=USER_FIELDS)
    validate(req.errors is None, req.raw)

    # add to groups
    for group in groups:
        req = client.mutation.addUserToGroup(
            userId=user["id"], groupId=group["id"])
        validate(req.errors is None, req.raw)

    # set password
    ret = subprocess.run([
        "ldappasswd",
        "-x",
        "-H", ldap_url,
        "-D", "uid=" + admin_username + ",ou=people," + base_dn,
        "-y", admin_password_file,
        "-T", password_file,
        "uid=" + user["id"] + ",ou=people," + base_dn
    ], capture_output=True)
    validate(ret.returncode == 0, "Error setting password for '" +
             user["id"] + "'.\n" + ret.stderr.decode("utf-8"))

    return user


def create_all_groups(groups: json, client: HTTPClient) -> dict:
    """ Create all groups with graphql """

    existing_groups: json = client.query.groups(GROUP_FIELDS).data["groups"]
    existing_groups_map: dict = {
        group["displayName"]: group for group in existing_groups}

    for must_exist_group in sorted(groups):
        if must_exist_group not in existing_groups_map:
            print(f"Group '{must_exist_group}' does not exist, creating...")
            group: json = client.mutation.createGroup(
                name=must_exist_group, _fields=GROUP_FIELDS).data["createGroup"]
            existing_groups_map[must_exist_group] = group
            print(f"\tGroup '{must_exist_group}' created.")
        else:
            print(f"Group '{must_exist_group}' exists, skipping")

    return existing_groups_map


def create_all_users(users: json, existing_groups_map: dict, ldap_url: str, base_dn: str, admin_username: str, admin_password_file: str, client: HTTPClient) -> dict:
    """ Create all users with graphql and ldappasswd"""

    existing_users: json = client.query.users(USER_FIELDS).data["users"]
    existing_users_map: dict = {user["id"]: user for user in existing_users}

    for must_exist_user in sorted(users, key=lambda x: x["id"]):
        must_exist_user_id: str = must_exist_user["id"]

        # Seed file groups is just a list of names, API returns id + displayName
        must_exist_user["groups"][:] = [
            existing_groups_map[group_name] for group_name in must_exist_user["groups"]
        ]

        if must_exist_user_id not in existing_users_map:
            print(f"User '{must_exist_user_id}' does not exist, creating...")
            user = create_single_user(must_exist_user, ldap_url, base_dn,
                               admin_username, admin_password_file, client)
            existing_users_map[must_exist_user_id] = user
            print(f"\tUser '{must_exist_user_id}' created.")
        else:
            print(f"User '{must_exist_user_id}' exists, skipping")

    return existing_users_map


def main() -> int:
    """Echo the input arguments to standard output"""

    configuration = validateConfiguration(CONFIG_FILE, ADMIN_PASSWORD)
    client = createauthenticatedWebClient(
        configuration["admin_username"], configuration["web_url"], ADMIN_PASSWORD)
    configuration_groups = configuration["seed"].get("groups", [])
    configuration_users = configuration["seed"].get("users", [])
    groups = create_all_groups(configuration_groups, client)
    users = create_all_users(configuration_users, groups,
                             configuration["ldap_url"], configuration["base_dn"], configuration["admin_username"], ADMIN_PASSWORD, client)
    print("Finished: " + str(len(users)) + " users and " + str(len(groups)) + " groups.")
    return 0


if __name__ == '__main__':
    exit(main())
